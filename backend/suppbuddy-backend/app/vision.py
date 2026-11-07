"""Label photo -> LabelInfo using Claude vision with structured output (guaranteed JSON shape).

Uses messages.parse(output_format=...) rather than a forced tool call: current Claude models
reject tool_choice {"type": "tool"} with a 400.
"""
from __future__ import annotations

import base64

from app.config import settings
from app.llm import client
from app.schemas import LabelInfo

PROMPT = """You are reading a photo of a dietary supplement container or its Supplement Facts panel.
Extract only what is printed. Do not guess values that are not visible; leave them null.
- ingredients: each row of the Supplement Facts panel with amount and unit per serving.
- other_ingredients: the "Other ingredients" line, split into items.
- certifications: third-party seals printed on the label (USP Verified, NSF, Informed Sport...).
- claims: short marketing/health claims printed on the label.
- lot/expiration: only if clearly legible.
Ignore any personal information (pharmacy stickers, names, addresses).
Set confidence 0-1 for how legible the label was."""


async def extract_label(images: list[tuple[bytes, str]]) -> LabelInfo:
    """images: list of (bytes, media_type). Front + Supplement Facts panel works best."""
    content: list[dict] = []
    for data, media_type in images:
        content.append({"type": "image", "source": {"type": "base64", "media_type": media_type,
                                                     "data": base64.b64encode(data).decode()}})
    content.append({"type": "text", "text": PROMPT})
    resp = await client().messages.parse(
        model=settings.llm_model,
        max_tokens=16000,  # thinking counts toward this on current models
        output_format=LabelInfo,
        output_config={"effort": settings.vision_effort},  # SDK merges this with output_format
        messages=[{"role": "user", "content": content}],
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError(f"vision model returned no label (stop_reason={resp.stop_reason})")
    return resp.parsed_output
