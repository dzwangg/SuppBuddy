"""Thin Claude client wrapper. Swap provider here if you move to OpenAI/Gemini."""
from __future__ import annotations

from functools import lru_cache

from app.config import settings


class LLMUnavailable(RuntimeError):
    pass


@lru_cache
def client():
    if not settings.anthropic_api_key:
        raise LLMUnavailable("ANTHROPIC_API_KEY not set")
    import anthropic
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


def available() -> bool:
    return bool(settings.anthropic_api_key)
