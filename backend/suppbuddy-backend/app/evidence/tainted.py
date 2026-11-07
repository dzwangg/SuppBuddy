"""FDA "Tainted Products Marketed as Dietary Supplements" list, loaded from a local CSV.

Local on purpose: it's small, changes slowly, and the demo must not depend on FDA's site.
Populate data/tainted_supplements.csv with scripts/import_tainted.py (see README).
Columns: date,product_name,company,hidden_ingredients,category,url
"""
from __future__ import annotations

import csv
import difflib
from functools import lru_cache

from app.config import settings

CSV_PATH = settings.data_dir / "tainted_supplements.csv"


@lru_cache
def _rows() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("product_name")]


def reload() -> int:
    _rows.cache_clear()
    return len(_rows())


def _sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def lookup(product_name: str | None, brand: str | None) -> list[dict]:
    """Return product-level matches (severe) and company-level matches (concerning)."""
    out = []
    for r in _rows():
        p = _sim(product_name or "", r["product_name"]) if product_name else 0.0
        c = _sim(brand or "", r.get("company") or "") if brand else 0.0
        if p >= 0.85 or (p >= 0.6 and c >= 0.85):
            out.append({**r, "match_type": "product", "match_score": round(max(p, c), 2)})
        elif c >= 0.9:
            out.append({**r, "match_type": "company", "match_score": round(c, 2)})
    return sorted(out, key=lambda r: (r["match_type"] != "product", -r["match_score"]))[:10]


def status() -> dict:
    return {"path": str(CSV_PATH), "rows": len(_rows())}
