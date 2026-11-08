"""Protocol v3 (dark + white/red/green/blue cycles): new sensor features, QC, product identity,
single-feature deviations and the confirm hold."""
import copy

from app import sim
from app.fingerprints import gtin14, product_key
from app.schemas import DeviceReadings, SamplePrep
from app.scoring.accuracy import score_against_crowd
from app.sensors.features import extract_features


def _feat(profile, prep=None, **kw):
    raw = sim.generate(profile, jitter=False, seed=1, **kw)
    return extract_features(DeviceReadings.model_validate(raw), prep)


# ---- features ----------------------------------------------------------------------------------
def test_cycle_mode_uses_colored_leds_for_color():
    r = _feat("b_complex")
    assert r.ok, r.qc_flags
    assert abs(r.features["A_B"] - 0.90) < 0.05 and abs(r.features["A_R"] - 0.05) < 0.03
    assert not r.qc_warnings


def test_scatter_color_separates_fine_haze_from_coarse_grains():
    protein = _feat("protein").features["scatter_exp"]
    starch = _feat("vitamin_c_cornstarch").features["scatter_exp"]
    assert protein > 2.0 and starch < 0.8


def test_residual_cloudiness_separates_soluble_from_filler():
    genuine = _feat("creatine").features
    cut = _feat("creatine_cornstarch").features
    assert genuine["S_residual"] < 0.15 and cut["S_residual"] > 0.5


def test_clear_samples_have_no_scatter_color_or_settling():
    # too little scatter above water for the exponent or settling rate to mean anything
    f = _feat("creatine").features
    assert f["scatter_exp"] is None and f["settle_rate"] is None


def test_light_leak_fails_the_scan():
    r = _feat("vitamin_c", leak=60)
    assert not r.ok
    assert any("light_leak" in f for f in r.qc_flags)


def test_dim_blue_led_falls_back_to_white_light():
    raw = sim.generate("b_complex", jitter=False, seed=1)
    raw["blank"]["b"] = dict(raw["dark"])  # blue LED never lit
    r = extract_features(DeviceReadings.model_validate(raw))
    assert r.ok, r.qc_flags
    assert any("weak_led_b" in w for w in r.qc_warnings)
    assert abs(r.features["A_B"] - 0.90) < 0.05


def test_saturation_limit_follows_reported_integration_time():
    raw = sim.generate("vitamin_c", jitter=False, seed=1)
    raw["samples"][6]["g"] = 21200  # over 97.6% of 21,504 at 50 ms
    assert not extract_features(DeviceReadings.model_validate(raw)).ok
    raw["tcs_integration_ms"] = 154  # 64 cycles -> 65,535 ceiling
    r = extract_features(DeviceReadings.model_validate(raw))
    assert not any("saturated" in f for f in r.qc_flags)
    assert any("sensor_settings_differ" in w for w in r.qc_warnings)


def test_heavier_scoop_is_rescaled_to_standard_prep():
    base = _feat("b_complex").features
    raw = sim.generate("b_complex", jitter=False, seed=1)
    double = copy.deepcopy(raw)
    for s in double["samples"]:  # twice the powder: twice the absorbance
        if s["led"] == "off":
            continue
        blank = double["blank"][s["led"]]
        # white readings use all three channels; each colored LED only its own
        for ch in (("r", "g", "b") if s["led"] == "white" else (s["led"],)):
            t = (s[ch] - raw["dark"][ch]) / (blank[ch] - raw["dark"][ch])
            s[ch] = raw["dark"][ch] + (blank[ch] - raw["dark"][ch]) * t ** 2
    r = extract_features(DeviceReadings.model_validate(double), SamplePrep(mass_mg=1000, volume_ml=50))
    assert abs(r.features["A_B"] - base["A_B"]) < 0.03
    assert r.features["ratio_BR"] == base["ratio_BR"] or abs(r.features["ratio_BR"] - base["ratio_BR"]) < 0.5
    assert r.features["conc_factor"] == 2.0


# ---- product identity --------------------------------------------------------------------------
def test_barcode_is_the_product_identity():
    assert gtin14("7 00580 72363 3") == "00700580723633"
    assert gtin14("0700580723633") == "00700580723633"  # EAN-13 form a scanner returns
    assert gtin14("700580723634") is None  # wrong check digit (misread label)
    assert product_key("ON", "Gold Standard 100% Whey", upc="700580723633") == "upc:00700580723633"
    assert product_key("ON", "Gold Standard Whey", upc="700580723633") == "upc:00700580723633"


def test_flavor_separates_products_without_a_barcode():
    choc = product_key("ON", "Gold Standard", flavor="Double Rich Chocolate")
    van = product_key("ON", "Gold Standard", flavor="Vanilla Ice Cream")
    assert choc != van and choc.endswith("|double-rich-chocolate")
    assert product_key("ON", "Gold Standard") == "on|gold-standard"  # unchanged format without flavor


# ---- scoring -----------------------------------------------------------------------------------
def test_one_feature_far_off_is_enough():
    stats = {k: {"mean": 1.0, "std": 0.1, "n": 5} for k in
             ("A_R", "A_G", "A_B", "ratio_BR", "ratio_GR", "S_final", "t90_s", "plateau_noise",
              "scatter_exp", "S_residual", "settle_rate", "S_noise")}
    features = {k: 1.0 for k in stats}
    features["S_final"] = 1.6  # z = 6 on cloudiness alone; RMS over 12 features is only ~1.7
    acc = score_against_crowd(features, stats, 5, False)
    assert acc.distance < 3 and acc.max_z == 6.0
    assert acc.label == "inconsistent"


# ---- API ---------------------------------------------------------------------------------------
def _post(client, profile, seed, label=None):
    body = {"label": label or sim.PROFILES[profile]["label"], "readings": sim.generate(profile, seed=seed),
            "synthetic": True}
    r = client.post("/scans?wait=true", json=body)
    assert r.status_code == 202, r.text
    return r.json()


def test_creatine_class_fallback_flags_starch(client):
    label = {"brand": "NoRefYet", "product_name": "Creatine Monohydrate"}
    good = _post(client, "creatine", 5, label)["report"]
    assert good["accuracy"]["reference"] == "class" and good["accuracy"]["label"] == "consistent"
    bad = _post(client, "creatine_cornstarch", 6, label)["report"]
    assert bad["accuracy"]["label"] == "inconsistent"
    assert any("starch" in i for i in bad["quality"]["issues"])


def test_outlier_confirm_is_held_then_forced(client):
    for seed in range(5):
        s = _post(client, "creatine", 200 + seed)
        assert client.post(f"/scans/{s['id']}/confirm").json()["held"] is False
    pid = s["product_id"]
    n_before = client.get(f"/products/{pid}/fingerprint").json()["n"]

    cut = _post(client, "creatine_cornstarch", 300)
    assert cut["report"]["verdict"] == "WARNING"
    r = client.post(f"/scans/{cut['id']}/confirm").json()
    assert r["held"] is True and "held for review" in r["reason"]
    assert client.get(f"/products/{pid}/fingerprint").json()["n"] == n_before
    assert client.get(f"/scans/{cut['id']}").json()["stages"]["confirm"]["status"] == "held"

    forced = client.post(f"/scans/{cut['id']}/confirm", json={"force": True}).json()
    assert forced["held"] is False and forced["n"] == n_before + 1
