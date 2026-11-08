"""Crowd fingerprints: running mean/variance per product per protocol (Welford's algorithm).

Only CONFIRMED, QC-passing scans update a fingerprint, and a confirmed scan far from an established
fingerprint is held for review instead of merged (main.py, /confirm). Those are the defenses against
garbage and against someone poisoning the crowd DB.

Product identity: the barcode when there is a valid one (it's printed per flavor and size, and reads
the same every time), otherwise brand + product name + flavor as read off the label.
"""
from __future__ import annotations

import math
import re

from sqlalchemy.orm import Session

from app.config import FEATURE_KEYS, settings
from app.db import Fingerprint, Product


def gtin14(code: str | None) -> str | None:
    """A UPC/EAN as 14 digits, or None if it isn't a valid barcode (bad length or check digit, e.g. a
    misread label)."""
    digits = re.sub(r"\D", "", code or "")
    if len(digits) not in (8, 12, 13, 14) or not digits.strip("0"):
        return None
    g = digits.zfill(14)
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(g[:13]))
    return g if (10 - total % 10) % 10 == int(g[13]) else None


def product_key(brand: str | None, name: str | None, upc: str | None = None,
                flavor: str | None = None) -> str | None:
    g = gtin14(upc)
    if g:
        return f"upc:{g}"

    def norm(s: str | None) -> str:
        return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    b, n, f = norm(brand), norm(name), norm(flavor)
    if not b and not n:
        return None
    return f"{b}|{n}|{f}" if f else f"{b}|{n}"


def get_or_create_product(s: Session, brand: str | None, name: str | None, label: dict | None,
                          upc: str | None = None, flavor: str | None = None) -> Product | None:
    key = product_key(brand, name, upc, flavor)
    if key is None:
        return None
    p = s.get(Product, key)
    if p is None:
        p = Product(id=key, brand=brand, name=name, label=label)
        s.add(p)
        s.flush()
    return p


def get_fingerprint(s: Session, product_id: str, protocol: str | None = None) -> Fingerprint | None:
    return s.get(Fingerprint, (product_id, protocol or settings.protocol_version))


def update_fingerprint(s: Session, product_id: str, features: dict, protocol: str, synthetic: bool) -> Fingerprint:
    fp = s.get(Fingerprint, (product_id, protocol))
    if fp is None:
        fp = Fingerprint(product_id=product_id, protocol=protocol, n=0, mean={}, m2={}, counts={}, synthetic=False)
        s.add(fp)
    mean, m2, counts = dict(fp.mean), dict(fp.m2), dict(fp.counts)
    for k in FEATURE_KEYS:
        x = features.get(k)
        if x is None:
            continue
        n = counts.get(k, 0) + 1
        mu = mean.get(k, 0.0)
        delta = x - mu
        mu += delta / n
        m2[k] = m2.get(k, 0.0) + delta * (x - mu)
        mean[k], counts[k] = mu, n
    fp.mean, fp.m2, fp.counts = mean, m2, counts  # reassign so SQLAlchemy sees the JSON change
    fp.n = (fp.n or 0) + 1
    fp.synthetic = bool(fp.synthetic) or synthetic
    s.flush()
    return fp


def fingerprint_stats(fp: Fingerprint) -> dict:
    out = {}
    for k in FEATURE_KEYS:
        n = fp.counts.get(k, 0)
        if n == 0:
            continue
        var = fp.m2.get(k, 0.0) / (n - 1) if n > 1 else 0.0
        out[k] = {"mean": round(fp.mean[k], 5), "std": round(math.sqrt(max(var, 0.0)), 5), "n": n}
    return out
