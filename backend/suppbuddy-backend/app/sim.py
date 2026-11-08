"""Fake device readings so the app and backend can be built before the rig works.

Physics is simplified on purpose:
  absorbance  A(t) = A_final * (1 - exp(-t/tau))                       (color appears as it dissolves)
  cloudiness  S(t) = 1 + X_final + (X_peak - X_final) * exp(-t/tau)    (undissolved powder clears)
              with X = S - 1, and under an LED of wavelength L the excess scales as (525/L)^exp:
              fine particles (exp 2-4) scatter blue much more than red, coarse grains (exp ~0) don't.
Profiles are made up. Do not present simulated scans as real (the API marks them synthetic).
TODO(calibrate): once the rig runs, replace PROFILES with numbers fit from real scans so the
simulator stays a useful offline test fixture.
"""
from __future__ import annotations

import math
import random

# A = (A_R, A_G, A_B) at plateau, S = cloudiness vs water at the end, S_peak = right after mixing,
# tau = dissolution time constant (s), exp = scatter color exponent
PROFILES: dict[str, dict] = {
    "water":               {"A": (0.00, 0.00, 0.00), "S": 1.0, "S_peak": 1.0, "tau": 5, "exp": 0.0,
                            "label": {"brand": "Tap", "product_name": "Water", "ingredients": []}},
    "b_complex":           {"A": (0.05, 0.15, 0.90), "S": 1.6, "S_peak": 2.5, "tau": 15, "exp": 2.0,
                            "label": {"brand": "DemoLabs", "product_name": "B-Complex 100",
                                      "ingredients": [{"name": "Riboflavin", "amount": 100, "unit": "mg"}]}},
    "vitamin_c":           {"A": (0.01, 0.01, 0.03), "S": 1.1, "S_peak": 2.5, "tau": 5, "exp": 1.5,
                            "label": {"brand": "DemoLabs", "product_name": "Vitamin C 1000",
                                      "ingredients": [{"name": "Vitamin C (as ascorbic acid)", "amount": 1000, "unit": "mg"}]}},
    "vitamin_c_cornstarch": {"A": (0.08, 0.09, 0.12), "S": 4.5, "S_peak": 6.0, "tau": 8, "exp": 0.4,
                            "label": {"brand": "DemoLabs", "product_name": "Vitamin C 1000",
                                      "ingredients": [{"name": "Vitamin C (as ascorbic acid)", "amount": 1000, "unit": "mg"}]}},
    "iron":                {"A": (0.12, 0.20, 0.45), "S": 2.2, "S_peak": 3.5, "tau": 25, "exp": 1.5,
                            "label": {"brand": "DemoLabs", "product_name": "Iron 65",
                                      "ingredients": [{"name": "Iron (as ferrous sulfate)", "amount": 65, "unit": "mg"}]}},
    "protein":             {"A": (0.30, 0.35, 0.45), "S": 12.0, "S_peak": 16.0, "tau": 20, "exp": 2.5,
                            "label": {"brand": "DemoLabs", "product_name": "Whey Isolate",
                                      "ingredients": [{"name": "Whey protein isolate", "amount": 25, "unit": "g"}]}},
    "creatine":            {"A": (0.01, 0.01, 0.02), "S": 1.08, "S_peak": 3.0, "tau": 10, "exp": 1.0,
                            "label": {"brand": "DemoLabs", "product_name": "Creatine Monohydrate",
                                      "ingredients": [{"name": "Creatine monohydrate", "amount": 5, "unit": "g"}]}},
    "creatine_cornstarch": {"A": (0.05, 0.06, 0.08), "S": 3.8, "S_peak": 5.5, "tau": 12, "exp": 0.4,
                            "label": {"brand": "DemoLabs", "product_name": "Creatine Monohydrate",
                                      "ingredients": [{"name": "Creatine monohydrate", "amount": 5, "unit": "g"}]}},
}

# Counts kept under the TCS34725's ceiling at 50 ms (21,504), clear channel included.
DARK = {"r": 300.0, "g": 320.0, "b": 280.0, "c": 900.0, "scatter": 40.0, "ir": 20.0}
BLANK = {"r": 6000.0, "g": 7000.0, "b": 5000.0, "c": 18855.0, "scatter": 400.0, "ir": 30.0}
# Water blank under each LED alone (cycle and sequential modes): mostly its own color band.
LED_BLANK = {
    "white": BLANK,
    "r": {"r": 5200.0, "g": 600.0, "b": 300.0, "c": 6500.0, "scatter": 380.0, "ir": 28.0},
    "g": {"r": 700.0, "g": 6200.0, "b": 900.0, "c": 8200.0, "scatter": 390.0, "ir": 27.0},
    "b": {"r": 300.0, "g": 1100.0, "b": 5600.0, "c": 7400.0, "scatter": 360.0, "ir": 26.0},
}
WAVELENGTH = {"white": 525.0, "r": 625.0, "g": 525.0, "b": 465.0}
CYCLE = ("off", "white", "r", "g", "b")
READING_S = 0.285  # the real tester takes ~285 ms per reading, so one cycle is ~1.43 s


def generate(profile: str, device_id: str = "sim-001", duration_s: int = 90, hz: float = 1.0,
             led_mode: str = "cycle", seed: int | None = None, jitter: bool = True,
             leak: float = 0.0) -> dict:
    """leak > 0 adds room light that ramps up over the second half of the run (for QC tests)."""
    rng = random.Random(seed)
    p = PROFILES[profile]
    j = (lambda x, f: x * (1 + rng.gauss(0, f))) if jitter else (lambda x, f: x)
    A = [j(a, 0.04) for a in p["A"]]
    x_final = j(p["S"] - 1, 0.06)
    x_peak = max(x_final, j(p["S_peak"] - 1, 0.06))
    tau = max(1.0, j(p["tau"], 0.10))
    exp_ = p["exp"] + (rng.gauss(0, 0.1) if jitter else 0.0)

    def light(t: float, duration: float) -> float:
        return leak * max(0.0, (t - duration / 2) / (duration / 2))

    def reading(t: float, led: str) -> dict:
        extra = light(t, duration_s)
        if led == "off":
            vals = {k: DARK[k] + rng.gauss(0, 3) for k in ("r", "g", "b", "scatter", "ir")}
            vals["c"] = DARK["c"] + rng.gauss(0, 5)
            vals["scatter"] += extra
            vals["c"] += extra * 10
            vals["ir"] += extra
            return vals
        blank = LED_BLANK[led] if led_mode != "white" else BLANK
        frac = 1 - math.exp(-t / tau)
        vals = {}
        for k, a in zip(("r", "g", "b"), A):
            vals[k] = DARK[k] + (blank[k] - DARK[k]) * 10 ** (-a * frac) + rng.gauss(0, 25)
        lit = sum(vals[k] - DARK[k] for k in ("r", "g", "b"))
        vals["c"] = DARK["c"] + (blank["c"] - DARK["c"]) * lit / sum(blank[k] - DARK[k] for k in ("r", "g", "b"))
        x = (x_final + (x_peak - x_final) * math.exp(-t / tau)) * (525.0 / WAVELENGTH[led]) ** exp_
        vals["scatter"] = DARK["scatter"] + (blank["scatter"] - DARK["scatter"]) * (1 + x) + rng.gauss(0, 4) + extra
        vals["ir"] = blank["ir"] + rng.gauss(0, 2) + extra
        return vals

    samples = []
    if led_mode == "cycle":
        t = 0.0
        while t < duration_s:
            for i, led in enumerate(CYCLE):
                ti = t + i * READING_S
                samples.append({"t_ms": int(ti * 1000), "led": led, **{k: round(v, 1) for k, v in reading(ti, led).items()}})
            t += READING_S * len(CYCLE)
        blank = {led: LED_BLANK[led] for led in ("white", "r", "g", "b")}
    else:
        n = int(duration_s * hz)
        for i in range(n):
            t = i / hz
            led = "white" if led_mode == "white" else ("r", "g", "b")[i % 3]
            samples.append({"t_ms": int(t * 1000), "led": led, **{k: round(v, 1) for k, v in reading(t, led).items()}})
        blank = {"white": BLANK} if led_mode == "white" else {k: LED_BLANK[k] for k in ("r", "g", "b")}

    return {"device_id": device_id, "protocol": "v3" if led_mode == "cycle" else "v1", "led_mode": led_mode,
            "tcs_gain": 4, "tcs_integration_ms": 50, "tsl_gain": 25, "tsl_integration_ms": 100,
            "dark": DARK, "blank": blank, "samples": samples}
