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

    # --- What the scatter says about undissolved particles ------------------------------------
    resid, exp_, settle, s_noise = (features.get(k) for k in ("S_residual", "scatter_exp", "settle_rate", "S_noise"))
    z_resid, z_exp, z_settle = _z(resid, fp_stats, "S_residual"), _z(exp_, fp_stats, "scatter_exp"), _z(settle, fp_stats, "settle_rate")
    if z_resid is not None:
        if z_resid > 3:
            issues.append(f"More of the cloudiness stayed than in other scans of this product (z={z_resid:.1f}). "
                          "Possible insoluble filler.")
            penalty += 2
    elif resid is not None and resid > settings.residual_high and (exp_ is None or exp_ < settings.coarse_scatter_exp):
        # Without a reference: lasting cloudiness from coarse particles. Fine natural haze (protein,
        # exponent 2+) is left alone; the crowd reference judges that.
        issues.append(f"The cloudiness didn't clear ({resid:.0%} of it remained) and looks about the same in blue "
                      "and red light, which is typical of an insoluble filler such as starch or flour.")
        penalty += 1
    if z_exp is not None and z_exp < -3:
        issues.append(f"Particles are coarser than in other scans of this product (z={z_exp:.1f}); "
                      "starch or flour grains scatter like this.")
        penalty += 1
    if (z_settle is not None and z_settle > 3) or (z_settle is None and settle is not None and settle > settings.settle_high):
        issues.append(f"Solids were still sinking at the end of the run (cloudiness falling {settle:.0%} per minute).")
        penalty += 1
    if s_noise is not None and s_noise > settings.scatter_noise_high:
        issues.append(f"The scattered light flickered ({s_noise:.0%}): grains or clumps drifting through the beam.")
        penalty += 1

    for w in (qc or {}).get("warnings", []):
        issues.append(f"Scan note: {w}")

    label = "good" if penalty == 0 else "fair" if penalty == 1 else "poor"
    return QualityScore(label=label, issues=issues,
                        metrics={"S_final": S, "t90_s": t90, "plateau_noise": noise, "S_residual": resid,
                                 "scatter_exp": exp_, "settle_rate": settle, "S_noise": s_noise})
