"""Quality = does the sample behave like a well-made product (dissolves, no excess filler, stable)?

Uses the crowd fingerprint when available (relative judgments), otherwise absolute thresholds.
TODO(calibrate): absolute thresholds in config.py are guesses until you have real scans.
"""
from __future__ import annotations

from app.config import settings
from app.schemas import QualityScore


def _z(x, st, key):
    if x is None or not st or key not in st or st[key]["n"] < settings.min_fingerprint_n:
        return None
    return (x - st[key]["mean"]) / max(st[key]["std"], settings.std_floor.get(key, 0.01))


def score_quality(features: dict | None, qc: dict | None, fp_stats: dict | None) -> QualityScore:
    if not features:
        return QualityScore(label="unknown", issues=["No usable sensor reading."])

    issues, penalty = [], 0
    S, t90, noise = features.get("S_final"), features.get("t90_s"), features.get("plateau_noise")

    zS = _z(S, fp_stats, "S_final")
    if zS is not None:
        if zS > 3:
            issues.append(f"Much cloudier than other scans of this product (z={zS:.1f}). Possible extra filler.")
            penalty += 2
        elif zS > 2:
            issues.append(f"Cloudier than usual for this product (z={zS:.1f}).")
            penalty += 1
    elif S is not None and S > settings.turbidity_high:
        issues.append(f"High turbidity ({S:.1f}x water). Lots of undissolved material.")
        penalty += 1

    zt = _z(t90, fp_stats, "t90_s")
    if zt is not None and abs(zt) > 2.5:
        word = "slower" if zt > 0 else "faster"
        issues.append(f"Dissolves {word} than other scans of this product (z={zt:.1f}).")
        penalty += 1
    elif t90 is None and features.get("A_final", 0) > 0.05:
        issues.append("Did not reach a stable reading during the run.")
        penalty += 1

    if noise is not None and noise > settings.plateau_noise_high:
        issues.append("Unstable final reading (clumping, bubbles, or settling).")
        penalty += 1

    for w in (qc or {}).get("warnings", []):
        issues.append(f"Scan note: {w}")

    label = "good" if penalty == 0 else "fair" if penalty == 1 else "poor"
    return QualityScore(label=label, issues=issues,
                        metrics={"S_final": S, "t90_s": t90, "plateau_noise": noise})
