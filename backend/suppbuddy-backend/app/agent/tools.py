"""Client-side tools the research agent can call. Each returns JSON-serializable data.

Stage 2 already ran the obvious lookups; their results are handed to the agent up front
(like Peel did), so the agent only calls these to chase gaps (e.g. a different brand spelling).
"""
from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from app.db import session
from app.evidence import dsld, openfda, tainted
from app.fingerprints import fingerprint_stats, get_fingerprint, product_key

TOOL_SPECS: list[dict] = [
    {
        "name": "crowd_stats",
        "description": "Get the crowdsourced optical fingerprint (per-feature mean/std/n) for a product.",
        "input_schema": {"type": "object", "properties": {
            "brand": {"type": "string"}, "product_name": {"type": "string"}}, "required": ["brand", "product_name"]},
    },
    {
        "name": "tainted_lookup",
        "description": "Search the FDA list of products marketed as supplements that contained hidden drugs.",
        "input_schema": {"type": "object", "properties": {
            "product_name": {"type": "string"}, "brand": {"type": "string"}}},
    },
    {
        "name": "fda_recalls",
        "description": "Search openFDA food/supplement recall enforcement reports by brand/firm name.",
        "input_schema": {"type": "object", "properties": {
            "brand": {"type": "string"}, "product_name": {"type": "string"}}, "required": ["brand"]},
    },
    {
        "name": "fda_adverse_events",
        "description": "Count FDA CAERS adverse event reports for a supplement brand, with top reactions.",
        "input_schema": {"type": "object", "properties": {"brand": {"type": "string"}}, "required": ["brand"]},
    },
    {
        "name": "dsld_search",
        "description": "Search the NIH Dietary Supplement Label Database for registered labels.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "dsld_label",
        "description": "Fetch one registered label (ingredients and amounts) from NIH DSLD by id.",
        "input_schema": {"type": "object", "properties": {"dsld_id": {"type": "string"}}, "required": ["dsld_id"]},
    },
]

SUBMIT_REPORT = {
    "name": "submit_report",
    "description": "Submit the final user-facing write-up. Call exactly once, at the end.",
    "strict": True,  # schema-valid input; the replacement for a forced tool call on current models
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "headline": {"type": "string", "description": "Max 8 words, consistent with the given verdict."},
            "summary": {"type": "string", "description": "2-4 plain-language sentences, max 90 words."},
            "key_findings": {"type": "array", "items": {"type": "string"}, "description": "Up to 6."},
            "advice": {"type": "array", "items": {"type": "string"}, "description": "Up to 2; the measured advice is kept."},
            "citations": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
                "source": {"type": "string"}, "title": {"type": "string"}, "url": {"type": "string"}},
                "required": ["source"]}},
        },
        "required": ["headline", "summary", "key_findings", "advice", "citations"],
    },
}


async def _crowd_stats(brand: str, product_name: str) -> dict:
    key = product_key(brand, product_name)
    with session() as s:
        fp = get_fingerprint(s, key) if key else None
        if not fp:
            return {"product_id": key, "n": 0}
        return {"product_id": key, "n": fp.n, "synthetic": fp.synthetic, "features": fingerprint_stats(fp)}


async def _tainted(product_name: str | None = None, brand: str | None = None) -> list:
    return tainted.lookup(product_name, brand)


async def _recalls(brand: str, product_name: str | None = None) -> list:
    return await openfda.recalls(brand, product_name)


async def _caers(brand: str) -> dict | None:
    return await openfda.caers(brand)


async def _dsld_search(query: str) -> list:
    return await dsld.search(query)


async def _dsld_label(dsld_id: str) -> dict:
    if not str(dsld_id).isdigit():  # it goes into a URL path
        raise ValueError("dsld_id must be numeric")
    return await dsld.get_label(dsld_id)


HANDLERS: dict[str, Callable[..., Awaitable[Any]]] = {
    "crowd_stats": _crowd_stats,
    "tainted_lookup": _tainted,
    "fda_recalls": _recalls,
    "fda_adverse_events": _caers,
    "dsld_search": _dsld_search,
    "dsld_label": _dsld_label,
}


async def run_tool(name: str, args: dict) -> tuple[str, bool]:
    """Returns (json_text, is_error). Truncated so one big result can't blow the context."""
    fn = HANDLERS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name}"}), True
    try:
        out = await fn(**args)
        return json.dumps(out, default=str)[:12000], False
    except Exception as e:  # noqa: BLE001 - tool errors go back to the model
        return json.dumps({"error": f"{type(e).__name__}: {e}"}), True
