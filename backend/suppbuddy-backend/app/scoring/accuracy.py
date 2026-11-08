"""Accuracy = does this sample behave like other samples of the same product?

Primary: diagonal-Mahalanobis distance against the crowd fingerprint (needs n >= min_fingerprint_n).
Fallback: range check against a hand-written ingredient-class reference.

This is NOT "is the label true". Be precise in UI copy: "consistent with N prior scans".
"""
from __future__ import annotations

import json
import math
from functools import lru_cache

from app.config import FEATURE_KEYS, settings
from app.schemas import AccuracyScore, LabelInfo


@lru_cache
def class_references() -> list[dict]:
    path = settings.data_dir / "class_references.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())["classes"]


def match_class(label: LabelInfo | None) -> dict | None:
    if label is None:
        return None
    text = " ".join(
        [label.product_name or ""] + [i.name for i in label.ingredients] + label.other_ingredients
    ).lower()
    best, best_hits = None, 0
    for cls in class_references():
        hits = sum(1 for kw in cls["keywords"] if kw in text)
        if hits > best_hits:
            best, best_hits = cls, hits
    return best


LABEL_ORDER = ["consistent", "borderline", "inconsistent"]


def _label_from_distance(d: float) -> str:
    if d <= settings.z_consistent:
        return "consistent"
    if d <= settings.z_borderline:
        return "borderline"
    return "inconsistent"


def _label_from_max(z: float) -> str:
    if z > settings.z_single_inconsistent:
        return "inconsistent"
    if z > settings.z_single_borderline:
        return "borderline"
    return "consistent"


def score_against_crowd(features: dict, stats: dict, n: int, synthetic: bool) -> AccuracyScore:
    zs = []
    for k in FEATURE_KEYS:
        x, st = features.get(k), stats.get(k)
        if x is None or st is None or st["n"] < settings.min_fingerprint_n:
            continue
        std = max(st["std"], settings.std_floor.get(k, 0.01))
        zs.append((k, (x - st["mean"]) / std, x, st["mean"]))
    if not zs:
        return AccuracyScore(label="insufficient_data", reference="crowd", reference_n=n,
                             reference_synthetic=synthetic, note="No overlapping features with the fingerprint.")
    d = math.sqrt(sum(z * z for _, z, _, _ in zs) / len(zs))  # RMS z, scale-free across feature count
    top = sorted(zs, key=lambda r: -abs(r[1]))[:3]
    max_z = abs(top[0][1])
    # The worse of the two: a broad drift across features, or one feature far off on its own.
    label = max(_label_from_distance(d), _label_from_max(max_z), key=LABEL_ORDER.index)
    return AccuracyScore(
        label=label,
        distance=round(d, 3),
        max_z=round(max_z, 2),
        reference="crowd",
        reference_n=n,
        reference_synthetic=synthetic,
        top_deviations=[{"feature": k, "z": round(z, 2), "value": v, "expected": round(m, 4)} for k, z, v, m in top],
        note=f"Compared with {n} confirmed scans of this product.",
    )


def score_against_class(features: dict, cls: dict) -> AccuracyScore:
    misses = []
    for k, (lo, hi) in cls["ranges"].items():
        x = features.get(k)
        if x is None:
            continue
        if not (lo <= x <= hi):
            misses.append({"feature": k, "value": x, "expected_range": [lo, hi]})
    n_checked = sum(1 for k in cls["ranges"] if features.get(k) is not None)
    if n_checked == 0:
        label = "insufficient_data"
    elif not misses:
        label = "consistent"
    elif len(misses) == 1 and n_checked > 1:
        label = "borderline"
    else:
        label = "inconsistent"
    return AccuracyScore(
        label=label,
        reference="class",
        top_deviations=misses,
        note=f"No crowd data yet. Compared with a rough reference for {cls['name']} ({cls['why']}) "
             "These ranges are uncalibrated.",
    )


def score_accuracy(features: dict | None, fp_stats: dict | None, fp_n: int, fp_synthetic: bool,
                   label: LabelInfo | None) -> AccuracyScore:
    if not features:
        return AccuracyScore(label="not_measured", note="No usable sensor reading.")
    if fp_stats and fp_n >= settings.min_fingerprint_n:
        return score_against_crowd(features, fp_stats, fp_n, fp_synthetic)
    cls = match_class(label)
    if cls:
        res = score_against_class(features, cls)
        res.reference_n = fp_n
        return res
    return AccuracyScore(
        label="insufficient_data",
        reference="none",
        reference_n=fp_n,
        note=f"Only {fp_n} prior scans of this product; need {settings.min_fingerprint_n}. "
             "Confirm this scan to help build the reference.",
    )
