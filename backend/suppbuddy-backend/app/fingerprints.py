"""Crowd fingerprints: running mean/variance per product per protocol (Welford's algorithm).

Only CONFIRMED, QC-passing scans update a fingerprint. That is the main defense against garbage
(and against someone poisoning the crowd DB). TODO(calibrate): once you have enough data, add an
outlier gate so a confirmed scan with z > 4 is held for review instead of merged.
"""
from __future__ import annotations

import math
import re

from sqlalchemy.orm import Session

from app.config import FEATURE_KEYS, settings
from app.db import Fingerprint, Product


def product_key(brand: str | None, name: str | None) -> str | None:
    def norm(s: str | None) -> str:
        return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    b, n = norm(brand), norm(name)
    if not b and not n:
        return None
    return f"{b}|{n}"


def get_or_create_product(s: Session, brand: str | None, name: str | None, label: dict | None) -> Product | None:
    key = product_key(brand, name)
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
