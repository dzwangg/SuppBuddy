"""API contracts. These are the shapes to agree on with David (app/ESP32) and Trevor (LCD).

If the firmware sends something different, change it HERE first; everything else reads these models.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Device payload (ESP32 -> phone -> backend)
# ---------------------------------------------------------------------------
class ChannelSnapshot(BaseModel):
    """One averaged reading of both sensors. TCS34725 (in line) gives r,g,b,c; TSL2591 (90 deg) gives
    scatter (its full-spectrum channel) and ir (its infrared-only channel)."""
    r: float
    g: float
    b: float
    c: float = 0.0
    scatter: float
    ir: float | None = None


class RawSample(BaseModel):
    t_ms: int = Field(..., description="ms since the sample run started")
    r: float
    g: float
    b: float
    c: float = 0.0
    scatter: float
    ir: float | None = None
    # Which LED was on. "white" = the white LED (or all LEDs together on older rigs); "off" = a dark
    # reading taken during the run (protocol v3 takes one every cycle).
    led: Literal["white", "r", "g", "b", "off"] = "white"
    temp_c: float | None = None


class DeviceReadings(BaseModel):
    device_id: str
    protocol: str = "v1"
    # "white": every sample has the white light on; read the r/g/b sensor channels.
    # "sequential_rgb": each sample has one colored LED on; use the matching sensor channel.
    # "cycle" (protocol v3): every ~1.4 s the tester takes a dark reading, then one reading each under
    #   white, red, green and blue light. Uses everything: colored LEDs for clean per-band absorbance and
    #   scatter color, white for dissolving speed and cloudiness, dark readings to follow room light.
    led_mode: Literal["white", "sequential_rgb", "cycle"] = "white"
    # Sensor settings the firmware used (its "I" line). Saturation limits are derived from these, and a
    # scan taken with settings different from the reference settings gets a warning.
    tcs_gain: float | None = None
    tcs_integration_ms: float | None = None
    tsl_gain: float | None = None
    tsl_integration_ms: float | None = None
    dark: ChannelSnapshot  # LEDs off, taken with the blank
    # Water blank, keyed by LED: "white" in white mode, "r"/"g"/"b" in sequential mode, all four in cycle mode
    blank: dict[str, ChannelSnapshot]
    samples: list[RawSample]


class SamplePrep(BaseModel):
    """How the sample was prepared. Defaults of the locked protocol live in config.py (sample_mass_mg,
    sample_volume_ml). When mass and volume are sent, concentration-dependent features are rescaled to
    the standard concentration, so a heavier or lighter scoop doesn't look like a different product."""
    mass_mg: float | None = None
    volume_ml: float | None = None
    stirred: bool | None = None
    temp_c: float | None = None  # water temperature; creatine solubility depends on it
    form: Literal["capsule_powder", "crushed_tablet", "powder", "liquid", "gummy", "other"] | None = None


# ---------------------------------------------------------------------------
# Label (photo -> vision -> structured)
# ---------------------------------------------------------------------------
class LabelIngredient(BaseModel):
    name: str
    amount: float | None = None
    unit: str | None = None


class LabelInfo(BaseModel):
    brand: str | None = None
    product_name: str | None = None
    # Part of the product identity when there's no barcode: chocolate and vanilla of one product
    # look completely different to the sensors, so they need separate references.
    flavor: str | None = None
    form: str | None = None  # capsule, tablet, powder...
    serving_size: str | None = None
    ingredients: list[LabelIngredient] = []
    other_ingredients: list[str] = []
    lot: str | None = None
    upc: str | None = None
    expiration: str | None = None
    certifications: list[str] = []  # e.g. "USP Verified", "NSF Certified for Sport" as printed
    claims: list[str] = []          # marketing claims as printed
    confidence: float | None = None  # model's self-reported 0-1


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------
class ScanCreate(BaseModel):
    label: LabelInfo | None = None
    readings: DeviceReadings | None = None
    sample_prep: SamplePrep | None = None
    product_id: str | None = None  # if the user picked an existing product
    synthetic: bool = False        # set by the simulator so fake data is never mistaken for real


class ConfirmRequest(BaseModel):
    product_id: str | None = None  # override if the label read was wrong
    # A scan that's far from an established reference is held instead of merged (it could be a fake,
    # a bad prep, or someone poisoning the data). force=True merges it anyway, after review.
    force: bool = False


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
class Verdict(str, Enum):
    CONSISTENT = "CONSISTENT"
    CHECK = "CHECK"
    WARNING = "WARNING"
    NO_REF = "NO_REF"        # nothing to compare against yet
    BAD_SCAN = "BAD_SCAN"    # QC failed, rescan


class AccuracyScore(BaseModel):
    label: Literal["consistent", "borderline", "inconsistent", "insufficient_data", "not_measured"]
    distance: float | None = None  # RMS z-score across features
    max_z: float | None = None     # largest single-feature |z|; one strong deviation is enough to flag
    reference: Literal["crowd", "class", "none"] = "none"
    reference_n: int = 0
    reference_synthetic: bool = False
    top_deviations: list[dict] = []
    note: str = ""


class QualityScore(BaseModel):
    label: Literal["good", "fair", "poor", "unknown"]
    issues: list[str] = []
    metrics: dict = {}


class ReputabilityScore(BaseModel):
    label: Literal["trusted", "mixed", "concerning", "severe", "unknown"]
    score: int | None = None  # 0-100
    findings: list[dict] = []


class Citation(BaseModel):
    source: str
    title: str | None = None
    url: str | None = None


class Report(BaseModel):
    verdict: Verdict
    headline: str
    summary: str
    accuracy: AccuracyScore
    quality: QualityScore
    reputability: ReputabilityScore
    key_findings: list[str] = []
    advice: list[str] = []
    citations: list[Citation] = []
    disclaimer: str = (
        "SuppBuddy compares your sample to other scans of the same product and to public safety "
        "records. It cannot confirm identity, purity, or dose like a certified lab can."
    )
    generated_by: Literal["deterministic", "agent"] = "deterministic"


class LcdMessage(BaseModel):
    """What Trevor's LCD shows. TODO(lcd): set line width to the real display (16x2 assumed)."""
    code: str
    line1: str
    line2: str
