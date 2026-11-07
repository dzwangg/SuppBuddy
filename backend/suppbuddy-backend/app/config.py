"""Central config. Everything tunable lives here or in .env.

Grep the repo for `TODO(` to find every assumption that needs real data.
Tags: TODO(hardware) TODO(protocol) TODO(mobile) TODO(lcd) TODO(calibrate) TODO(verify-api)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    # --- infra ---
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'suppbuddy.db'}")
    data_dir: Path = ROOT / "data"

    # --- LLM (Claude) ---
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    llm_model: str = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
    # Server-side web search tool. Set to "" to disable. 20260209 is the current version for
    # Sonnet 5.5 / Opus 5.5 (built-in result filtering); older models need web_search_20250305.
    web_search_tool_type: str = os.getenv("WEB_SEARCH_TOOL_TYPE", "web_search_20260209")
    agent_max_turns: int = int(os.getenv("AGENT_MAX_TURNS", "6"))
    # The agent only explains a verdict that's already set, so medium effort is plenty and keeps it fast.
    agent_effort: str = os.getenv("AGENT_EFFORT", "medium")
    # Copying text off a label needs little reasoning; the default (high) took about 60 s per photo.
    vision_effort: str = os.getenv("VISION_EFFORT", "low")
    # The phone shows the deterministic report within seconds; this only bounds the explanation.
    agent_timeout_s: float = float(os.getenv("AGENT_TIMEOUT_S", "90"))

    # --- external evidence ---
    openfda_api_key: str | None = os.getenv("OPENFDA_API_KEY") or None  # optional, raises rate limit
    evidence_offline: bool = _bool("EVIDENCE_OFFLINE")  # skip all network lookups (tests, flaky wifi)
    http_timeout_s: float = float(os.getenv("HTTP_TIMEOUT_S", "8"))
    cache_ttl_hours: float = float(os.getenv("CACHE_TTL_HOURS", "24"))

    # --- sensor protocol ---
    protocol_version: str = os.getenv("PROTOCOL_VERSION", "v1")
    # TODO(hardware): TCS34725 is 16-bit; its real ceiling depends on integration time
    # (max count = min(65535, 1024 * cycles)). Set from the integration time Akshay/Kevin pick.
    tcs_saturation: float = float(os.getenv("TCS_SATURATION", "65000"))
    # TODO(hardware): TSL2591 full-spectrum channel, 16-bit. Same caveat for gain/integration.
    tsl_saturation: float = float(os.getenv("TSL_SATURATION", "65000"))
    min_samples: int = 10
    min_blank_signal: float = 50.0  # blank - dark must exceed this or the LED/sensor is not working
    plateau_window_s: float = 10.0

    # --- scoring thresholds ---  TODO(calibrate): tune after 20+ real scans
    min_fingerprint_n: int = 3
    z_consistent: float = 1.5
    z_borderline: float = 3.0
    # std floors so a tight fingerprint (n=3) does not make tiny noise look like fraud
    std_floor: dict = field(default_factory=lambda: {
        "A_R": 0.02, "A_G": 0.02, "A_B": 0.02,
        "ratio_BR": 0.15, "ratio_GR": 0.15,
        "S_final": 0.10, "t90_s": 8.0, "plateau_noise": 0.005,
    })
    turbidity_high: float = 2.0      # S_final (scatter vs water blank) above this = cloudy
    plateau_noise_high: float = 0.03  # absorbance std on plateau above this = clumping / bubbles


settings = Settings()

# Features used in the fingerprint vector. Order matters only for display.
FEATURE_KEYS = ["A_R", "A_G", "A_B", "ratio_BR", "ratio_GR", "S_final", "t90_s", "plateau_noise"]
