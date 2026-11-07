"""Tiny DB-backed cache so the demo doesn't depend on live APIs and repeat scans cost nothing."""
from __future__ import annotations

import hashlib
import json
import time

from app.config import settings
from app.db import CacheEntry, session


def _key(namespace: str, payload) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return f"{namespace}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


def cache_get(namespace: str, payload, ttl_hours: float | None = None):
    ttl = (ttl_hours or settings.cache_ttl_hours) * 3600
    with session() as s:
        e = s.get(CacheEntry, _key(namespace, payload))
        if e and time.time() - e.fetched_at < ttl:
            return e.value
    return None


def cache_set(namespace: str, payload, value) -> None:
    with session() as s:
        s.merge(CacheEntry(key=_key(namespace, payload), value=value, fetched_at=time.time()))


class OfflineMiss(RuntimeError):
    """Raised on a cache miss while EVIDENCE_OFFLINE=1."""


def require_online(namespace: str) -> None:
    if settings.evidence_offline:
        raise OfflineMiss(f"{namespace}: offline and not cached")
