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
    """One averaged reading of both sensors. TCS34725 gives r,g,b,c; TSL2591 gives scatter."""
    r: float
    g: float
    b: float
    c: float = 0.0
    scatter: float


class RawSample(BaseModel):
    t_ms: int = Field(..., description="ms since sample was added to the cuvette")
    r: float
    g: float
    b: float
    c: float = 0.0
    scatter: float
    # Which LED was on for this sample. "white" = all three RGB LEDs on together.
    # TODO(protocol): confirm with Akshay/Kevin whether LEDs run together or cycle R->G->B.
    led: Literal["white", "r", "g", "b"] = "white"
    temp_c: float | None = None


class DeviceReadings(BaseModel):
    device_id: str
    protocol: str = "v1"
    # "white": every sample has all LEDs on, read r/g/b sensor channels.
    # "sequential_rgb": each sample has one LED on; we use the matching sensor channel.
    led_mode: Literal["white", "sequential_rgb"] = "white"
    # TODO(hardware): firmware should report the gain/integration it actually used so we can
    # reject scans taken with different settings than the fingerprint.
    tcs_gain: int | None = None
    tcs_integration_ms: float | None = None
    tsl_gain: str | None = None
    tsl_integration_ms: float | None = None
    dark: ChannelSnapshot  # LEDs off
    # Water blank, keyed by LED ("white" in white mode, "r"/"g"/"b" in sequential mode)
    blank: dict[str, ChannelSnapshot]
    samples: list[RawSample]


class SamplePrep(BaseModel):
    # TODO(protocol): lock these with the hardware team. Crowd data is useless if prep varies.
    mass_mg: float | None = None
    volume_ml: float | None = None
    stirred: bool | None = None
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
    distance: float | None = None
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
