"""NIH Dietary Supplement Label Database (DSLD). Public, no auth.

Verified 2026-11-07: /search-filter?q=&size= returns {"hits":[{"_id","_source":{"fullName","brandName"}}]}
and /label/{id} returns ingredientRows[].quantity as a list of {quantity, unit, ...}.
"""
from __future__ import annotations

import difflib

import httpx

from app.config import settings
from app.evidence.cache import cache_get, cache_set, require_online
from app.schemas import LabelInfo

BASE = "https://api.ods.od.nih.gov/dsld/v9"


async def search(query: str, size: int = 10) -> list[dict]:
    if (hit := cache_get("dsld_search", {"q": query, "size": size}, ttl_hours=168)) is not None:
        return hit
    require_online("dsld_search")
    async with httpx.AsyncClient(timeout=settings.http_timeout_s) as client:
        r = await client.get(f"{BASE}/search-filter", params={"q": query, "size": size})
    r.raise_for_status()
    data = r.json()
    hits = data.get("hits") if isinstance(data, dict) else data
    if isinstance(hits, dict):
        hits = hits.get("hits", [])
    out = []
    for h in hits or []:
        src = h.get("_source", h)
        out.append({
            "dsld_id": str(h.get("_id") or src.get("id") or ""),
            "product_name": src.get("fullName") or src.get("productName"),
            "brand": src.get("brandName") or src.get("brand"),
            "off_market": src.get("offMarket"),
            "entry_date": src.get("entryDate"),
        })
    cache_set("dsld_search", {"q": query, "size": size}, out)
    return out


async def get_label(dsld_id: str) -> dict:
    # v2: entries carry the barcode (upc)
    if (hit := cache_get("dsld_label", {"id": dsld_id, "v": 2}, ttl_hours=168)) is not None:
        return hit
    require_online("dsld_label")
    async with httpx.AsyncClient(timeout=settings.http_timeout_s) as client:
        r = await client.get(f"{BASE}/label/{dsld_id}")
    r.raise_for_status()
    data = r.json()
    rows = []
    for row in data.get("ingredientRows") or []:
        qty = (row.get("quantity") or [{}])
        q0 = qty[0] if isinstance(qty, list) and qty else (qty if isinstance(qty, dict) else {})
        rows.append({"name": row.get("name"), "amount": q0.get("quantity"), "unit": q0.get("unit")})
    out = {"dsld_id": dsld_id, "product_name": data.get("fullName"), "brand": data.get("brandName"),
           "upc": data.get("upcSku"), "ingredients": rows}
    cache_set("dsld_label", {"id": dsld_id, "v": 2}, out)
    return out


def upc_format(code: str | None) -> str | None:
    """Scanners give UPC-A as 12 digits or EAN-13 with a leading 0; DSLD stores "7 00580 72363 3"."""
    d = "".join(c for c in (code or "") if c.isdigit())
    if len(d) == 13 and d[0] == "0":
        d = d[1:]
    if len(d) != 12 or set(d) == {"0"}:  # all zeros is a placeholder some DSLD entries use
        return None
    return f"{d[0]} {d[1:6]} {d[6:11]} {d[11]}"


async def by_barcode(code: str) -> dict | None:
    """Registered label whose barcode matches exactly, preferring on-market and newest versions."""
    upc = upc_format(code)
    if not upc:
        return None
    hits = await search(f'"{upc}"')  # quoted: unquoted digit groups match unrelated labels
    hits.sort(key=lambda h: h.get("entry_date") or "", reverse=True)  # newest first...
    hits.sort(key=lambda h: h.get("off_market") or 0)                  # ...then on-market first (stable)
    for h in hits[:3]:  # search is full-text, so confirm the barcode on the record itself
        reg = await get_label(h["dsld_id"])
        if reg.get("upc") == upc:
            return reg
    return None


def _sim(a: str | None, b: str | None) -> float:
    return difflib.SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def compare_labels(photo: LabelInfo, registered: dict) -> list[str]:
    """Flag ingredients whose printed amount differs >15% from the registered label."""
    mismatches = []
    reg = {(r["name"] or "").lower(): r for r in registered.get("ingredients", [])}
    for ing in photo.ingredients:
        if ing.amount is None:
            continue
        match = max(reg, key=lambda k: _sim(k, ing.name), default=None)
        if not match or _sim(match, ing.name) < 0.75:
            continue
        r = reg[match]
        try:
            ra = float(r["amount"])
        except (TypeError, ValueError):
            continue
        if ra > 0 and (r.get("unit") or "").lower() == (ing.unit or "").lower() and abs(ing.amount - ra) / ra > 0.15:
            mismatches.append(f"Photo label says {ing.amount} {ing.unit} {ing.name}; registered label says {ra} {r['unit']}.")
    return mismatches


async def lookup(label: LabelInfo) -> dict:
    if label.upc and (reg := await by_barcode(label.upc)):
        base = {"dsld_id": reg["dsld_id"], "product_name": reg["product_name"], "brand": reg["brand"],
                "matched_by": "barcode"}
        if label.brand and _sim(reg["brand"], label.brand) < 0.6:
            return {**base, "found": False, "mismatches": [], "barcode_owner_mismatch":
                    f"This barcode is registered to {reg['brand']} {reg['product_name']} in the NIH label "
                    f"database, but the label says {label.brand} {label.product_name or ''}. "
                    "That can mean a relabeled or counterfeit bottle; rescan to rule out a mix-up."}
        return {**base, "found": True, "mismatches": compare_labels(label, reg)}
    q = " ".join(x for x in [label.brand, label.product_name] if x)
    if not q:
        return {"found": False}
    hits = await search(q)
    best = max(hits, key=lambda h: 0.4 * _sim(h["brand"], label.brand) + 0.6 * _sim(h["product_name"], label.product_name),
               default=None)
    # Brand must match too: generic names ("Riboflavin 100 mg") exist under many brands, and
    # crediting another brand's label made a made-up brand look "registered".
    if (not best or _sim(best["product_name"], label.product_name) < 0.5
            or (label.brand and _sim(best["brand"], label.brand) < 0.6)):
        return {"found": False, "candidates": hits[:3]}
    reg = await get_label(best["dsld_id"])
    return {"found": True, "dsld_id": best["dsld_id"], "product_name": reg["product_name"],
            "brand": reg["brand"], "mismatches": compare_labels(label, reg)}
