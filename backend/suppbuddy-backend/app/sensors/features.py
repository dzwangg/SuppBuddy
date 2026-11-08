"""Raw readings -> QC + feature vector.

Physics:
  TCS34725 sits in line behind the cuvette -> transmitted light per band.
      A_c(t) = -log10( (I_c(t) - dark_c(t)) / (I0_c - dark0_c) )      c in {R,G,B}
  TSL2591 sits at 90 deg -> scattered light (turbidity, undissolved filler).
      S(t)   = (scatter(t) - dark_s(t)) / (scatter_blank - dark0_s)   1.0 == clear water

What each feature tells you (protocol v3 "cycle" mode gets all of them):
  A_R, A_G, A_B      color: absorbance per band at the end of the run. In cycle mode each band is read with
                     its own LED through the matching sensor channel, which is cleaner than white light.
  ratio_BR, ratio_GR color shape, independent of how much powder went in
  S_final            cloudiness at the end: undissolved material, fillers, natural protein haze
  t90_s              dissolving speed (time to 90% of the final absorbance, white light)
  plateau_noise      unstable absorbance at the end: clumps, bubbles
  scatter_exp        scatter color exponent from the blue and red LEDs: ln(X_B/X_R) / ln(lambda_R/lambda_B)
                     with X = S - 1. Fine particles (protein haze) scatter blue much more (exponent 2-4);
                     coarse grains (starch, flour) scatter every color alike (exponent near 0).
  S_residual         share of the peak cloudiness still there at the end: (S_final - 1) / (S_peak - 1).
                     A genuine soluble powder clears (~0); insoluble filler doesn't (~1). It's a ratio,
                     so a heavier or lighter scoop barely moves it.
  settle_rate        how fast the excess cloudiness falls at the end (fraction per minute): solids sinking
  S_noise            scatter flicker on the plateau (std / mean): grains drifting through the beam

Dark readings taken every cycle (led "off") are subtracted at the time of each reading, which removes
slow room-light drift, and a dark reading that climbs fails the scan as a light leak.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app.config import settings
from app.schemas import ChannelSnapshot, DeviceReadings, RawSample, SamplePrep

CHANNELS = ("r", "g", "b")
T_MIN = 1e-4  # transmittance floor so log10 never explodes
# Features that scale with how much powder is in the water (rescaled to the standard prep).
CONCENTRATION_FEATURES = ("A_R", "A_G", "A_B", "A_final", "slope_max")


@dataclass
class FeatureResult:
    ok: bool
    features: dict = field(default_factory=dict)
    qc_flags: list[str] = field(default_factory=list)     # fatal problems
    qc_warnings: list[str] = field(default_factory=list)  # usable but suspicious
    series: dict = field(default_factory=dict)            # downsampled curves for the app's chart

    def qc_dict(self) -> dict:
        # the same warning can come from more than one light source; list it once
        return {"ok": self.ok, "flags": list(dict.fromkeys(self.qc_flags)),
                "warnings": list(dict.fromkeys(self.qc_warnings))}


# ---------------------------------------------------------------------------
# Sensor ceilings
# ---------------------------------------------------------------------------
def tcs_ceiling(integration_ms: float | None) -> float:
    if settings.tcs_saturation_override:
        return settings.tcs_saturation_override
    ms = integration_ms or settings.ref_tcs_integration_ms
    cycles = max(1, round(ms / 2.4))
    return min(65535, 1024 * cycles) * settings.saturation_margin


def tsl_ceiling(integration_ms: float | None) -> float:
    if settings.tsl_saturation_override:
        return settings.tsl_saturation_override
    ms = integration_ms or settings.ref_tsl_integration_ms
    return (37888 if ms < 150 else 65535) * settings.saturation_margin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _t(rows: list[RawSample]) -> np.ndarray:
    return np.array([s.t_ms / 1000.0 for s in rows], dtype=float)


def _y(rows: list[RawSample], attr: str) -> np.ndarray:
    return np.array([getattr(s, attr) or 0.0 for s in rows], dtype=float)


class _Dark:
    """Dark level per channel over time: interpolated from the run's dark readings when there are any,
    otherwise the single dark reading taken with the blank."""

    def __init__(self, readings: DeviceReadings):
        self.base = readings.dark
        off = [s for s in readings.samples if s.led == "off"]
        self.off = off if len(off) >= 2 else []

    def at(self, attr: str, t: np.ndarray) -> np.ndarray:
        if not self.off:
            return np.full_like(t, getattr(self.base, attr) or 0.0)
        return np.interp(t, _t(self.off), _y(self.off, attr))


def _time_to_fraction(t: np.ndarray, a: np.ndarray, a_final: float, frac: float) -> float | None:
    if abs(a_final) < 0.01:
        return None  # nothing dissolved enough to time it
    target = frac * a_final
    idx = np.where(a >= target)[0] if a_final > 0 else np.where(a <= target)[0]
    return float(t[idx[0]]) if idx.size else None


def _smooth(y: np.ndarray, k: int = 5) -> np.ndarray:
    if y.size < k:
        return y
    # edge-padded moving average, so the ends aren't pulled toward zero
    pad = k // 2
    padded = np.pad(y, pad, mode="edge")
    return np.convolve(padded, np.ones(k) / k, mode="valid")


def _downsample(t: np.ndarray, y: np.ndarray, n: int = 60) -> list[list[float]]:
    if t.size <= n:
        idx = np.arange(t.size)
    else:
        idx = np.linspace(0, t.size - 1, n).astype(int)
    return [[round(float(t[i]), 2), round(float(y[i]), 4)] for i in idx]


def _plateau_mask(t: np.ndarray) -> np.ndarray:
    mask = t >= (t[-1] - settings.plateau_window_s)
    if mask.sum() < 3:
        mask = np.zeros_like(t, dtype=bool)
        mask[-3:] = True
    return mask


def _robust_max(y: np.ndarray) -> float:
    """Second-largest value: one glitchy reading shouldn't fail a scan."""
    if y.size == 0:
        return 0.0
    return float(np.sort(y)[-2]) if y.size >= 3 else float(y.max())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def extract_features(readings: DeviceReadings, prep: SamplePrep | None = None) -> FeatureResult:
    res = FeatureResult(ok=True)
    mode = readings.led_mode
    lit = [s for s in readings.samples if s.led != "off"]

    if len(lit) < settings.min_samples:
        res.ok = False
        res.qc_flags.append(f"too_few_samples ({len(lit)} < {settings.min_samples})")
        return res

    dark0 = readings.dark
    dark = _Dark(readings)
    white_blank = readings.blank.get("white") or next(iter(readings.blank.values()))
    if mode == "white":
        white_rows = lit
    elif mode == "cycle":
        white_rows = [s for s in lit if s.led == "white"]
    else:
        white_rows = []

    _check_settings(readings, res)
    _check_saturation(readings, res)
    _check_light_leak(readings, white_blank, white_rows, res)

    # ---- Absorbance per band ------------------------------------------------
    def absorbance(rows: list[RawSample], ch: str, blank: ChannelSnapshot) -> tuple[np.ndarray, np.ndarray]:
        t = _t(rows)
        trans = (_y(rows, ch) - dark.at(ch, t)) / (getattr(blank, ch) - getattr(dark0, ch))
        if np.any(trans > 1.10):
            res.qc_warnings.append(f"transmission_above_blank_{ch} (blank drift or bubbles)")
        return t, -np.log10(np.clip(trans, T_MIN, None))

    def strong(blank: ChannelSnapshot | None, attr: str) -> bool:
        return blank is not None and getattr(blank, attr) - getattr(dark0, attr) >= settings.min_blank_signal

    band: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for ch in CHANNELS:
        if mode == "white":
            rows, blank = lit, white_blank
        elif mode == "sequential_rgb":
            rows, blank = [s for s in lit if s.led == ch], readings.blank.get(ch)
            if blank is None:
                res.ok = False
                res.qc_flags.append(f"missing blank for LED '{ch}' in sequential_rgb mode")
                continue
        else:  # cycle: the colored LED through its own channel when that LED is bright enough
            mono = [s for s in lit if s.led == ch]
            if mono and strong(readings.blank.get(ch), ch):
                rows, blank = mono, readings.blank[ch]
            else:
                rows, blank = white_rows, white_blank
                res.qc_warnings.append(f"weak_led_{ch} (its LED barely reached the sensor; used white light for this band)")
        if len(rows) < settings.min_samples:
            res.ok = False
            res.qc_flags.append(f"too_few_samples_{ch}")
            continue
        if not strong(blank, ch):
            res.ok = False
            res.qc_flags.append(f"weak_blank_{ch} (LED off or misaligned?)")
            continue
        band[ch] = absorbance(rows, ch, blank)

    # ---- Scatter (white light, or green in sequential mode) -------------------
    if mode == "sequential_rgb":
        s_rows = [s for s in lit if s.led == "g"] or lit
        s_blank = readings.blank.get("g") or white_blank
    else:
        s_rows, s_blank = white_rows, white_blank
    s_den = s_blank.scatter - dark0.scatter
    if s_den <= 0:
        res.ok = False
        res.qc_flags.append("scatter_blank_not_above_dark")

    if len(band) < 3 or s_den <= 0 or len(s_rows) < 3:
        res.ok = False
        return res

    t_s = _t(s_rows)
    s_norm = (_y(s_rows, "scatter") - dark.at("scatter", t_s)) / s_den

    # ---- Kinetics from one light source ---------------------------------------
    if mode == "sequential_rgb":
        t_ref = band["r"][0]
        comp = np.mean([np.interp(t_ref, *band[ch]) for ch in CHANNELS], axis=0)
    else:
        kin = [absorbance(white_rows, ch, white_blank)[1] for ch in CHANNELS]
        t_ref = _t(white_rows)
        comp = np.mean(kin, axis=0)
    comp_s = _smooth(comp)
    pm = _plateau_mask(t_ref)
    a_final = float(np.median(comp[pm]))

    dt = np.diff(t_ref)
    slope = np.diff(comp_s) / np.where(dt == 0, np.nan, dt)
    slope_max = float(np.nanmax(np.abs(slope))) if slope.size else 0.0
    noise = float(np.std(comp[pm]))

    A = {ch: float(np.median(band[ch][1][_plateau_mask(band[ch][0])])) for ch in CHANNELS}
    sp = _plateau_mask(t_s)
    S_final = float(np.median(s_norm[sp]))

    def ratio(num: float, den: float) -> float | None:
        return round(num / den, 4) if abs(den) >= 0.02 else None

    res.features = {
        "A_R": round(A["r"], 4),
        "A_G": round(A["g"], 4),
        "A_B": round(A["b"], 4),
        "ratio_BR": ratio(A["b"], A["r"]),
        "ratio_GR": ratio(A["g"], A["r"]),
        "S_final": round(S_final, 4),
        "A_final": round(a_final, 4),
        "t50_s": _time_to_fraction(t_ref, comp_s, a_final, 0.5),
        "t90_s": _time_to_fraction(t_ref, comp_s, a_final, 0.9),
        "slope_max": round(slope_max, 5),
        "plateau_noise": round(noise, 5),
        "duration_s": round(float(t_ref[-1] - t_ref[0]), 1),
        **_scatter_features(t_s, s_norm, S_final),
        "scatter_exp": _scatter_exponent(readings, lit, dark),
    }

    _normalize_to_standard_prep(prep, res)

    # Flat signal: looks like plain water. Peel rejected these; we do too.
    f = res.features
    if max(abs(f["A_R"]), abs(f["A_G"]), abs(f["A_B"])) < 0.01 and f["S_final"] < 1.05:
        res.ok = False
        res.qc_flags.append("flat_signal (sample looks like water; was it added?)")

    if f["duration_s"] < 30:
        res.qc_warnings.append("short_run (<30 s); dissolution timing unreliable")
    if f["t90_s"] is not None and f["t90_s"] > 0.9 * f["duration_s"]:
        res.qc_warnings.append("not_plateaued (still dissolving at end of run; extend run time)")

    res.series = {
        "absorbance": _downsample(t_ref, comp),
        "scatter": _downsample(t_s, s_norm),
    }
    return res


# ---------------------------------------------------------------------------
# QC checks
# ---------------------------------------------------------------------------
def _check_settings(readings: DeviceReadings, res: FeatureResult) -> None:
    reported = {
        "TCS gain": (readings.tcs_gain, settings.ref_tcs_gain),
        "TCS integration": (readings.tcs_integration_ms, settings.ref_tcs_integration_ms),
        "TSL gain": (readings.tsl_gain, settings.ref_tsl_gain),
        "TSL integration": (readings.tsl_integration_ms, settings.ref_tsl_integration_ms),
    }
    off = [f"{name} {got:g} (reference {want:g})" for name, (got, want) in reported.items()
           if got is not None and abs(got - want) > 1e-6]
    if off:
        res.qc_warnings.append("sensor_settings_differ: " + ", ".join(off) +
                               "; this scan may not compare with reference scans")


def _check_saturation(readings: DeviceReadings, res: FeatureResult) -> None:
    tcs_max = tcs_ceiling(readings.tcs_integration_ms)
    tsl_max = tsl_ceiling(readings.tsl_integration_ms)
    snaps: list = [readings.dark, *readings.blank.values(), *readings.samples]
    for ch in CHANNELS:
        if any(getattr(s, ch) >= tcs_max for s in snaps):
            res.ok = False
            res.qc_flags.append(f"saturated_{ch} (lower TCS gain or integration time)")
    if any(s.scatter >= tsl_max or (s.ir or 0) >= tsl_max for s in snaps):
        res.ok = False
        res.qc_flags.append("saturated_scatter (lower TSL2591 gain)")


def _check_light_leak(readings: DeviceReadings, white_blank: ChannelSnapshot, white_rows: list[RawSample],
                      res: FeatureResult) -> None:
    dark0 = readings.dark
    off = [s for s in readings.samples if s.led == "off"]
    ref_s = white_blank.scatter - dark0.scatter
    ref_c = (white_blank.c or 0.0) - (dark0.c or 0.0)
    if off and ref_s > 0:
        rise_s = _robust_max(_y(off, "scatter")) - dark0.scatter
        rise_c = _robust_max(_y(off, "c")) - (dark0.c or 0.0)
        if rise_s > settings.light_leak_frac * ref_s or (ref_c > 0 and rise_c > settings.light_leak_frac * ref_c):
            res.ok = False
            res.qc_flags.append("light_leak (room light reached the sensors during the run; close the lid and rescan)")
    # The LEDs give off almost no infrared, so infrared climbing above the blank's means outside light.
    irs = [s.ir for s in white_rows if s.ir is not None]
    if irs and white_blank.ir is not None and ref_s > 0:
        if float(np.median(irs)) - white_blank.ir > settings.light_leak_frac * ref_s:
            res.qc_warnings.append("infrared_rising (outside light may be getting into the box)")


# ---------------------------------------------------------------------------
# Scatter features
# ---------------------------------------------------------------------------
def _scatter_features(t: np.ndarray, s: np.ndarray, s_final: float) -> dict:
    out: dict = {"S_residual": None, "settle_rate": None, "S_noise": None}
    pm = _plateau_mask(t)
    mean_p = float(np.mean(s[pm]))
    if mean_p > 0:
        out["S_noise"] = round(float(np.std(s[pm])) / mean_p, 5)

    peak = float(np.max(_smooth(s)))
    if peak - 1 >= settings.residual_min_peak:
        out["S_residual"] = round(min(1.5, max(0.0, (s_final - 1) / (peak - 1))), 4)

    win = t >= (t[-1] - settings.settle_window_s)
    if win.sum() >= 3:
        excess = s[win] - 1
        mean_x = float(np.mean(excess))
        if mean_x >= settings.min_excess_scatter:
            slope = float(np.polyfit(t[win], excess, 1)[0])  # per second
            out["settle_rate"] = round(-slope * 60 / mean_x, 4)
    return out


def _scatter_exponent(readings: DeviceReadings, lit: list[RawSample], dark: _Dark) -> float | None:
    """Angstrom-style exponent of the excess scatter between the blue and red LEDs."""
    excess = {}
    for led in ("b", "r"):
        rows = [s for s in lit if s.led == led]
        blank = readings.blank.get(led)
        if len(rows) < 3 or blank is None:
            return None
        den = blank.scatter - readings.dark.scatter
        if den < settings.min_blank_signal / 10:  # water scatter is faint; this only rejects a dead LED
            return None
        t = _t(rows)
        s = (_y(rows, "scatter") - dark.at("scatter", t)) / den
        x = float(np.median(s[_plateau_mask(t)])) - 1
        if x < settings.min_excess_scatter:
            return None
        excess[led] = x
    wl = settings.led_wavelength_nm
    return round(math.log(excess["b"] / excess["r"]) / math.log(wl["r"] / wl["b"]), 3)


# ---------------------------------------------------------------------------
# Sample prep
# ---------------------------------------------------------------------------
def _normalize_to_standard_prep(prep: SamplePrep | None, res: FeatureResult) -> None:
    """Rescale concentration-dependent features to the standard prep (sample_mass_mg in sample_volume_ml).
    Absorbance scales linearly with concentration (Beer-Lambert); so does excess cloudiness at low
    turbidity. Ratios, timings and the scatter shape features don't need it."""
    if not prep or not prep.mass_mg or not prep.volume_ml:
        return
    k = (prep.mass_mg / prep.volume_ml) / (settings.sample_mass_mg / settings.sample_volume_ml)
    if abs(k - 1) <= settings.prep_tolerance:
        return
    if not (settings.prep_normalize_min <= k <= settings.prep_normalize_max):
        res.qc_warnings.append(
            f"sample_prep_off_protocol ({prep.mass_mg:g} mg in {prep.volume_ml:g} mL is {k:.2f}x the standard "
            f"{settings.sample_mass_mg:g} mg in {settings.sample_volume_ml:g} mL; too far off to correct)")
        return
    f = res.features
    for key in CONCENTRATION_FEATURES:
        if f.get(key) is not None:
            f[key] = round(f[key] / k, 5)
    f["S_final"] = round(1 + (f["S_final"] - 1) / k, 4)
    f["conc_factor"] = round(k, 4)
    res.qc_warnings.append(f"normalized_to_standard_prep ({k:.2f}x the standard concentration; "
                           "color and cloudiness rescaled)")
