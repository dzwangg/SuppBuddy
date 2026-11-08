"""openFDA: food/supplement recalls (enforcement) and CAERS adverse events. No key required.

Docs: https://open.fda.gov/apis/food/enforcement/  https://open.fda.gov/apis/food/event/
openFDA returns 404 when a search has zero matches; we treat that as an empty result.
"""
from __future__ import annotations

from collections import Counter
from urllib.parse import quote

import httpx

from app.config import settings
from app.evidence.cache import cache_get, cache_set, require_online

BASE = "https://api.fda.gov"
# Verified 2026-11-07 via https://api.fda.gov/food/event.json?count=products.industry_name.exact
SUPPLEMENT_INDUSTRY = "Vit/Min/Prot/Unconv Diet(Human/Animal)"
SERIOUS_MARKERS = ("death", "life threatening", "hospital", "disabil", "emergency", "intervention", "congenital")


def _q(term: str) -> str:
    return quote(term.replace('"', "").strip())


async def _get(path: str, search: str, limit: int) -> dict:
    url = f"{BASE}{path}?search={search}&limit={limit}"
    if settings.openfda_api_key:
        url += f"&api_key={settings.openfda_api_key}"
    async with httpx.AsyncClient(timeout=settings.http_timeout_s) as client:
        r = await client.get(url)
    if r.status_code == 404:
        return {"meta": {"results": {"total": 0}}, "results": []}
    if r.status_code >= 400:  # not raise_for_status(): its message includes the URL, api_key and all
        raise RuntimeError(f"openFDA HTTP {r.status_code}")
    return r.json()


async def recalls(brand: str | None, product: str | None = None, limit: int = 25) -> list[dict]:
    if not brand:
        return []
    key = {"brand": brand, "product": product, "v": 2}  # v2: entries carry event_id
    if (hit := cache_get("fda_recalls", key)) is not None:
        return hit
    require_online("fda_recalls")
    b = _q(brand)
    # Space (+) is OR in openFDA. Firm name OR product text mentions the brand.
    search = f'recalling_firm:"{b}"+product_description:"{b}"'
    data = await _get("/food/enforcement.json", search, limit)
    prod_tokens = [t for t in (product or "").lower().split() if len(t) > 3]
    out = []
    for r in data.get("results", []):
        desc = (r.get("product_description") or "").lower()
        out.append({
            "event_id": r.get("event_id"),  # one recall event spans many records (one per size/SKU)
            "recall_number": r.get("recall_number"),
            "classification": r.get("classification"),
            "status": r.get("status"),
            "reason_for_recall": r.get("reason_for_recall"),
            "report_date": r.get("report_date"),
            "recalling_firm": r.get("recalling_firm"),
            "product_description": (r.get("product_description") or "")[:300],
            "code_info": (r.get("code_info") or "")[:500],
            "product_specific": bool(prod_tokens) and sum(t in desc for t in prod_tokens) >= max(1, len(prod_tokens) // 2),
        })
    cache_set("fda_recalls", key, out)
    return out


async def caers(brand: str | None, limit: int = 100) -> dict | None:
    if not brand:
        return None
    key = {"brand": brand}
    if (hit := cache_get("fda_caers", key)) is not None:
        return hit
    require_online("fda_caers")
    b = _q(brand)
    search = f'products.name_brand:"{b}"+AND+products.industry_name:"{_q(SUPPLEMENT_INDUSTRY)}"'
    data = await _get("/food/event.json", search, limit)
    results = data.get("results", [])
    serious = 0
    reactions: Counter = Counter()
    for ev in results:
        outcomes = " ".join(ev.get("outcomes") or []).lower()
        if any(m in outcomes for m in SERIOUS_MARKERS):
            serious += 1
        reactions.update(ev.get("reactions") or [])
    out = {
        "total": data.get("meta", {}).get("results", {}).get("total", 0),
        "sample_size": len(results),
        "serious": serious,
        "top_reactions": reactions.most_common(8),
    }
    cache_set("fda_caers", key, out)
    return out
