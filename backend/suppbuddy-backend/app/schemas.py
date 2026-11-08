"""API contracts. These are the shapes to agree on with David (app/ESP32) and Trevor (LCD).

If the firmware sends something different, change it HERE first; everything else reads these models.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Bounds at the trust boundary: the phone and any other client post these as-is.
Short = Annotated[str, Field(max_length=300)]
FINITE = ConfigDict(allow_inf_nan=False)  # NaN/Infinity pass every QC comparison and break JSON responses


# ---------------------------------------------------------------------------
# Device payload (ESP32 -> phone -> backend)
# ---------------------------------------------------------------------------
class ChannelSnapshot(BaseModel):
    """One averaged reading of both sensors. TCS34725 (in line) gives r,g,b,c; TSL2591 (90 deg) gives
    scatter (its full-spectrum channel) and ir (its infrared-only channel)."""
    model_config = FINITE
    r: float
    g: float
    b: float
    c: float = 0.0
    scatter: float
    ir: float | None = None


class RawSample(BaseModel):
    model_config = FINITE
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
    device_id: str = Field(max_length=64)
    protocol: str = Field("v1", max_length=16)
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
    blank: dict[str, ChannelSnapshot] = Field(min_length=1)
    samples: list[RawSample] = Field(max_length=5000)


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
    name: Short
    amount: float | None = None
    unit: Short | None = None


class LabelInfo(BaseModel):
    brand: Short | None = None
    product_name: Short | None = None
    # Part of the product identity when there's no barcode: chocolate and vanilla of one product
    # look completely different to the sensors, so they need separate references.
    flavor: Short | None = None
    form: Short | None = None  # capsule, tablet, powder...
    serving_size: Short | None = None
    ingredients: list[LabelIngredient] = Field(default_factory=list, max_length=80)
    other_ingredients: list[Short] = Field(default_factory=list, max_length=80)
    lot: Short | None = None
    upc: Short | None = None
    expiration: Short | None = None
    certifications: list[Short] = Field(default_factory=list, max_length=40)  # e.g. "USP Verified" as printed
    claims: list[Short] = Field(default_factory=list, max_length=40)          # marketing claims as printed
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

    @field_validator("url")
    @classmethod
    def _web_only(cls, v: str | None) -> str | None:
        """The app renders these as tappable links and the agent can cite anything: keep http(s) with a host."""
        if v is None:
            return None
        u = urlparse(v.strip())
        return v.strip() if u.scheme in ("http", "https") and u.netloc else None


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
