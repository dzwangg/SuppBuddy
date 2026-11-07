"""Fake device readings so the app and backend can be built before the rig works.

Physics is simplified on purpose: first-order dissolution A(t) = A_final * (1 - exp(-t/tau)).
Profiles are made up. Do not present simulated scans as real (the API marks them synthetic).
TODO(calibrate): once the rig runs, replace PROFILES with numbers fit from real scans so the
simulator stays a useful offline test fixture.
"""
from __future__ import annotations

import math
import random

# A = (A_R, A_G, A_B) at plateau, S = scatter vs water blank, tau = dissolution time constant (s)
PROFILES: dict[str, dict] = {
    "water":               {"A": (0.00, 0.00, 0.00), "S": 1.0, "tau": 5,
                            "label": {"brand": "Tap", "product_name": "Water", "ingredients": []}},
    "b_complex":           {"A": (0.05, 0.15, 0.90), "S": 1.6, "tau": 15,
                            "label": {"brand": "DemoLabs", "product_name": "B-Complex 100",
                                      "ingredients": [{"name": "Riboflavin", "amount": 100, "unit": "mg"}]}},
    "vitamin_c":           {"A": (0.01, 0.01, 0.03), "S": 1.1, "tau": 5,
                            "label": {"brand": "DemoLabs", "product_name": "Vitamin C 1000",
                                      "ingredients": [{"name": "Vitamin C (as ascorbic acid)", "amount": 1000, "unit": "mg"}]}},
    "vitamin_c_cornstarch": {"A": (0.08, 0.09, 0.12), "S": 4.5, "tau": 8,
                            "label": {"brand": "DemoLabs", "product_name": "Vitamin C 1000",
                                      "ingredients": [{"name": "Vitamin C (as ascorbic acid)", "amount": 1000, "unit": "mg"}]}},
    "iron":                {"A": (0.12, 0.20, 0.45), "S": 2.2, "tau": 25,
                            "label": {"brand": "DemoLabs", "product_name": "Iron 65",
                                      "ingredients": [{"name": "Iron (as ferrous sulfate)", "amount": 65, "unit": "mg"}]}},
    "protein":             {"A": (0.30, 0.35, 0.45), "S": 12.0, "tau": 20,
                            "label": {"brand": "DemoLabs", "product_name": "Whey Isolate",
                                      "ingredients": [{"name": "Whey protein isolate", "amount": 25, "unit": "g"}]}},
}

DARK = {"r": 300.0, "g": 320.0, "b": 280.0, "c": 900.0, "scatter": 40.0}
BLANK = {"r": 18000.0, "g": 22000.0, "b": 15000.0, "c": 55000.0, "scatter": 400.0}


def generate(profile: str, device_id: str = "sim-001", duration_s: int = 90, hz: float = 1.0,
             led_mode: str = "white", seed: int | None = None, jitter: bool = True) -> dict:
    rng = random.Random(seed)
    p = PROFILES[profile]
    j = (lambda x, f: x * (1 + rng.gauss(0, f))) if jitter else (lambda x, f: x)
    A = [j(a, 0.04) for a in p["A"]]
    S = 1 + j(p["S"] - 1, 0.06)
    tau = max(1.0, j(p["tau"], 0.10))

    samples = []
    n = int(duration_s * hz)
    for i in range(n):
        t = i / hz
        frac = 1 - math.exp(-t / tau)
        leds = ["white"] if led_mode == "white" else [["r", "g", "b"][i % 3]]
        for led in leds:
            vals = {}
            for k, a in zip(("r", "g", "b"), A):
                trans = 10 ** (-a * frac)
                vals[k] = DARK[k] + (BLANK[k] - DARK[k]) * trans + rng.gauss(0, 25)
            vals["c"] = DARK["c"] + sum(vals[k] - DARK[k] for k in ("r", "g", "b")) * 1.05
            vals["scatter"] = DARK["scatter"] + (BLANK["scatter"] - DARK["scatter"]) * (1 + (S - 1) * frac) + rng.gauss(0, 4)
            samples.append({"t_ms": int(t * 1000), "led": led, **{k: round(v, 1) for k, v in vals.items()}})

    blank = {"white": BLANK} if led_mode == "white" else {k: BLANK for k in ("r", "g", "b")}
    return {"device_id": device_id, "protocol": "v1", "led_mode": led_mode,
            "dark": DARK, "blank": blank, "samples": samples}
