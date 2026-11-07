"""Raw readings -> QC + feature vector.

Physics:
  TCS34725 sits in line behind the cuvette -> transmitted light per band.
      A_c(t) = -log10( (I_c(t) - dark_c) / (I0_c - dark_c) )      c in {R,G,B}
  TSL2591 sits at 90 deg -> scattered light (turbidity, undissolved filler).
      S(t)   = (scatter(t) - dark_s) / (scatter_blank - dark_s)     1.0 == clear water

Composite absorbance A(t) = mean over channels drives the dissolution kinetics (t50, t90).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.config import settings
from app.schemas import DeviceReadings

CHANNELS = ("r", "g", "b")
T_MIN = 1e-4  # transmittance floor so log10 never explodes


@dataclass
class FeatureResult:
    ok: bool
    features: dict = field(default_factory=dict)
    qc_flags: list[str] = field(default_factory=list)     # fatal problems
    qc_warnings: list[str] = field(default_factory=list)  # usable but suspicious
    series: dict = field(default_factory=dict)            # downsampled curves for the app's chart

    def qc_dict(self) -> dict:
        return {"ok": self.ok, "flags": self.qc_flags, "warnings": self.qc_warnings}


def _channel_series(readings: DeviceReadings, ch: str) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Return (t_s, signal, dark, blank) for one color channel, respecting led_mode."""
    if readings.led_mode == "white":
        rows = readings.samples
        blank = readings.blank.get("white") or next(iter(readings.blank.values()))
    else:
        rows = [s for s in readings.samples if s.led == ch]
        blank = readings.blank.get(ch)
        if blank is None:
            raise ValueError(f"missing blank for LED '{ch}' in sequential_rgb mode")
    t = np.array([s.t_ms / 1000.0 for s in rows], dtype=float)
    y = np.array([getattr(s, ch) for s in rows], dtype=float)
    return t, y, getattr(readings.dark, ch), getattr(blank, ch)


def _scatter_series(readings: DeviceReadings) -> tuple[np.ndarray, np.ndarray, float, float]:
    rows = readings.samples
    if readings.led_mode == "white":
        blank = readings.blank.get("white") or next(iter(readings.blank.values()))
    else:
        # TODO(protocol): in sequential mode, which LED should drive the scatter reading?
        # Assumes green (middle of the TSL2591 response). Change if hardware uses a dedicated LED.
        rows = [s for s in rows if s.led == "g"] or rows
        blank = readings.blank.get("g") or next(iter(readings.blank.values()))
    t = np.array([s.t_ms / 1000.0 for s in rows], dtype=float)
    y = np.array([s.scatter for s in rows], dtype=float)
    return t, y, readings.dark.scatter, blank.scatter


def _time_to_fraction(t: np.ndarray, a: np.ndarray, a_final: float, frac: float) -> float | None:
    if abs(a_final) < 0.01:
        return None  # nothing dissolved enough to time it
    target = frac * a_final
    idx = np.where(a >= target)[0] if a_final > 0 else np.where(a <= target)[0]
    return float(t[idx[0]]) if idx.size else None


def _smooth(y: np.ndarray, k: int = 5) -> np.ndarray:
    if y.size < k:
        return y
    return np.convolve(y, np.ones(k) / k, mode="same")


def _downsample(t: np.ndarray, y: np.ndarray, n: int = 60) -> list[list[float]]:
    if t.size <= n:
        idx = np.arange(t.size)
    else:
        idx = np.linspace(0, t.size - 1, n).astype(int)
    return [[round(float(t[i]), 2), round(float(y[i]), 4)] for i in idx]


def extract_features(readings: DeviceReadings) -> FeatureResult:
    res = FeatureResult(ok=True)

    if len(readings.samples) < settings.min_samples:
        res.ok = False
        res.qc_flags.append(f"too_few_samples ({len(readings.samples)} < {settings.min_samples})")
        return res

    absorb: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for ch in CHANNELS:
        try:
            t, y, dark, blank = _channel_series(readings, ch)
        except ValueError as e:
            res.ok = False
            res.qc_flags.append(str(e))
            continue
        if t.size < settings.min_samples:
            res.ok = False
            res.qc_flags.append(f"too_few_samples_{ch}")
            continue
        if blank >= settings.tcs_saturation or np.any(y >= settings.tcs_saturation):
            res.ok = False
            res.qc_flags.append(f"saturated_{ch} (lower TCS gain or integration time)")
        if blank - dark < settings.min_blank_signal:
            res.ok = False
            res.qc_flags.append(f"weak_blank_{ch} (LED off or misaligned?)")
            continue
        trans = np.clip((y - dark) / (blank - dark), T_MIN, None)
        if np.any(trans > 1.10):
            res.qc_warnings.append(f"transmission_above_blank_{ch} (blank drift or bubbles)")
        absorb[ch] = (t, -np.log10(trans))

    t_s, y_s, dark_s, blank_s = _scatter_series(readings)
    if blank_s >= settings.tsl_saturation or np.any(y_s >= settings.tsl_saturation):
        res.ok = False
        res.qc_flags.append("saturated_scatter (lower TSL2591 gain)")
    if blank_s - dark_s <= 0:
        res.ok = False
        res.qc_flags.append("scatter_blank_not_above_dark")
        s_norm = None
    else:
        s_norm = (y_s - dark_s) / (blank_s - dark_s)

    if len(absorb) < 3 or s_norm is None:
        res.ok = False
        return res

    # Plateau = last N seconds of the run
    def plateau(t: np.ndarray, y: np.ndarray) -> np.ndarray:
        mask = t >= (t[-1] - settings.plateau_window_s)
        return y[mask] if mask.sum() >= 3 else y[-3:]

    A = {ch: float(np.median(plateau(*absorb[ch]))) for ch in CHANNELS}
    S_final = float(np.median(plateau(t_s, s_norm)))

    # Composite curve on a common time base (red channel's timestamps)
    t_ref = absorb["r"][0]
    comp = np.mean([np.interp(t_ref, *absorb[ch]) for ch in CHANNELS], axis=0)
    comp_s = _smooth(comp)
    a_final = float(np.median(plateau(t_ref, comp)))

    dt = np.diff(t_ref)
    slope = np.diff(comp_s) / np.where(dt == 0, np.nan, dt)
    slope_max = float(np.nanmax(np.abs(slope))) if slope.size else 0.0
    noise = float(np.std(plateau(t_ref, comp)))

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
    }

    # Flat signal: looks like plain water. Peel rejected these; we do too.
    if max(abs(v) for v in A.values()) < 0.01 and S_final < 1.05:
        res.ok = False
        res.qc_flags.append("flat_signal (sample looks like water; was it added?)")

    if res.features["duration_s"] < 30:
        res.qc_warnings.append("short_run (<30 s); dissolution timing unreliable")
    if res.features["t90_s"] is not None and res.features["t90_s"] > 0.9 * res.features["duration_s"]:
        res.qc_warnings.append("not_plateaued (still dissolving at end of run; extend run time)")

    res.series = {
        "absorbance": _downsample(t_ref, comp),
        "scatter": _downsample(t_s, s_norm),
    }
    return res
