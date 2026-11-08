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
    # Fingerprints are stored per protocol, so data from different rigs/preps never mix.
    # v3 = firmware/SupplementOpticalTester (dark + W/R/G/B cycle) with the locked sample prep below.
    protocol_version: str = os.getenv("PROTOCOL_VERSION", "v3")
    # Reference sensor settings: firmware/SupplementOpticalTester/Config.h. A scan reporting other
    # settings gets a warning, because its counts and noise won't compare with the reference data.
    ref_tcs_gain: float = float(os.getenv("REF_TCS_GAIN", "4"))
    ref_tcs_integration_ms: float = float(os.getenv("REF_TCS_INTEGRATION_MS", "50"))
    ref_tsl_gain: float = float(os.getenv("REF_TSL_GAIN", "25"))
    ref_tsl_integration_ms: float = float(os.getenv("REF_TSL_INTEGRATION_MS", "100"))
    # Sensor ceilings are derived from the integration time the scan reports (or the reference one):
    #   TCS34725: min(65535, 1024 x cycles of 2.4 ms) -> 21,504 at 50 ms
    #   TSL2591:  37,888 at 100 ms, 65,535 from 200 ms
    # and flagged at saturation_margin of that, where the response goes non-linear.
    # TCS_SATURATION / TSL_SATURATION in .env override the derived values.
    tcs_saturation_override: float | None = float(os.environ["TCS_SATURATION"]) if os.getenv("TCS_SATURATION") else None
    tsl_saturation_override: float | None = float(os.environ["TSL_SATURATION"]) if os.getenv("TSL_SATURATION") else None
    saturation_margin: float = 0.976
    min_samples: int = 10
    min_blank_signal: float = 50.0  # blank - dark must exceed this or the LED/sensor is not working
    plateau_window_s: float = 10.0
    # Room light reaching the sensors: a dark reading during the run that rises by more than this
    # fraction of the water-blank signal fails the scan.
    light_leak_frac: float = 0.05
    # LED peak wavelengths (nm), for the scatter color exponent. White is treated as green.
    led_wavelength_nm: dict = field(default_factory=lambda: {"r": 625.0, "g": 525.0, "b": 465.0, "white": 525.0})
    # Scatter above water (S - 1) needed before its color or settling means anything. Below this the
    # exponent and settling rate are mostly sensor noise (checked on simulated clear samples).
    min_excess_scatter: float = 0.15
    residual_min_peak: float = 0.10    # S_residual needs the cloudiness to have peaked at least this far above water
    settle_window_s: float = 20.0      # settling rate is fit over the last part of the run

    # --- sample prep (the locked protocol) ---  TODO(protocol): confirm with the team
    sample_mass_mg: float = float(os.getenv("SAMPLE_MASS_MG", "500"))
    sample_volume_ml: float = float(os.getenv("SAMPLE_VOLUME_ML", "50"))
    prep_tolerance: float = 0.10       # within 10% of the standard concentration: no note
    prep_normalize_min: float = 0.5    # rescale to standard concentration only between 0.5x and 2x
    prep_normalize_max: float = 2.0

    # --- scoring thresholds ---  TODO(calibrate): tune after 20+ real scans
    min_fingerprint_n: int = 3
    z_consistent: float = 1.5
    z_borderline: float = 3.0
    # One feature far off is enough, even when the RMS across all features looks fine (a filler mostly
    # moves cloudiness, and averaging it with the color features would hide it).
    z_single_borderline: float = 3.5
    z_single_inconsistent: float = 5.0
    # std floors so a tight fingerprint (n=3) does not make tiny noise look like fraud
    std_floor: dict = field(default_factory=lambda: {
        "A_R": 0.02, "A_G": 0.02, "A_B": 0.02,
        "ratio_BR": 0.15, "ratio_GR": 0.15,
        "S_final": 0.10, "t90_s": 8.0, "plateau_noise": 0.005,
        "scatter_exp": 0.4, "S_residual": 0.08, "settle_rate": 0.1, "S_noise": 0.01,
    })
    turbidity_high: float = 2.0      # S_final (scatter vs water blank) above this = cloudy
    plateau_noise_high: float = 0.03  # absorbance std on plateau above this = clumping / bubbles
    residual_high: float = 0.5       # more than half the initial cloudiness never cleared = insoluble material
    coarse_scatter_exp: float = 1.0  # scatter about the same in every color = coarse particles (starch, flour)
    settle_high: float = 0.3         # excess cloudiness falling >30%/min at the end = solids sinking
    scatter_noise_high: float = 0.05  # scatter flickering >5% on the plateau = grains drifting through the beam


settings = Settings()

# Features used in the fingerprint vector. Order matters only for display. Features that can't be
# measured on a scan (None) are skipped in comparisons.
FEATURE_KEYS = ["A_R", "A_G", "A_B", "ratio_BR", "ratio_GR", "S_final", "t90_s", "plateau_noise",
                "scatter_exp", "S_residual", "settle_rate", "S_noise"]
