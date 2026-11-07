from app import sim
from app.schemas import DeviceReadings
from app.sensors.features import extract_features


def _feat(profile, **kw):
    return extract_features(DeviceReadings.model_validate(sim.generate(profile, jitter=False, seed=1, **kw)))


def test_recovers_absorbance():
    r = _feat("b_complex")
    assert r.ok, r.qc_flags
    assert abs(r.features["A_B"] - 0.90) < 0.05
    assert abs(r.features["A_R"] - 0.05) < 0.03
    assert r.features["ratio_BR"] > 5


def test_scatter_and_kinetics():
    r = _feat("vitamin_c_cornstarch")
    assert r.ok
    assert abs(r.features["S_final"] - 4.5) < 0.3
    # first-order: t90 = tau * ln(10) ~= 18.4 s for tau=8
    assert 14 < r.features["t90_s"] < 23


def test_water_rejected_as_flat():
    r = _feat("water")
    assert not r.ok
    assert any("flat_signal" in f for f in r.qc_flags)


def test_sequential_led_mode():
    r = _feat("iron", led_mode="sequential_rgb", duration_s=120)
    assert r.ok, r.qc_flags
    assert abs(r.features["A_B"] - 0.45) < 0.05


def test_saturation_flag():
    raw = sim.generate("b_complex", seed=1)
    raw["samples"][5]["g"] = 65535
    r = extract_features(DeviceReadings.model_validate(raw))
    assert not r.ok
    assert any("saturated_g" in f for f in r.qc_flags)
