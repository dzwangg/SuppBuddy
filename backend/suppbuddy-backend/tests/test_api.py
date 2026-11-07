from app import sim
from app.evidence import tainted


def _post(client, profile, seed):
    body = {"label": sim.PROFILES[profile]["label"], "readings": sim.generate(profile, seed=seed), "synthetic": True}
    r = client.post("/scans?wait=true", json=body)
    assert r.status_code == 202, r.text
    return r.json()


def test_health(client):
    assert client.get("/health").json()["ok"]


def test_no_reference_then_class_fallback(client):
    scan = _post(client, "b_complex", seed=100)
    assert scan["status"] == "complete"
    rep = scan["report"]
    # No crowd data yet -> falls back to the riboflavin class reference
    assert rep["accuracy"]["reference"] == "class"
    assert rep["accuracy"]["label"] == "consistent"
    assert scan["lcd"]["line1"].strip()


def test_crowd_fingerprint_flow(client):
    # Build a reference from 5 confirmed genuine scans
    for seed in range(5):
        s = _post(client, "vitamin_c", seed=seed)
        r = client.post(f"/scans/{s['id']}/confirm")
        assert r.status_code == 200, r.text
    fp = client.get(f"/products/{s['product_id']}/fingerprint").json()
    assert fp["n"] == 5 and fp["synthetic"] is True

    good = _post(client, "vitamin_c", seed=42)["report"]
    assert good["accuracy"]["reference"] == "crowd"
    assert good["accuracy"]["label"] == "consistent"
    assert good["verdict"] in ("CONSISTENT", "CHECK")

    # Same label, cut with cornstarch -> should be flagged
    bad = _post(client, "vitamin_c_cornstarch", seed=43)["report"]
    assert bad["accuracy"]["label"] == "inconsistent"
    assert bad["verdict"] == "WARNING"
    assert any("cloud" in i.lower() for i in bad["quality"]["issues"])


def test_bad_scan_not_confirmable(client):
    s = _post(client, "water", seed=1)
    assert s["report"]["verdict"] == "BAD_SCAN"
    assert client.post(f"/scans/{s['id']}/confirm").status_code == 422


def test_tainted_hit_forces_warning(client, tmp_path, monkeypatch):
    csv = tmp_path / "t.csv"
    csv.write_text("date,product_name,company,hidden_ingredients,category,url\n"
                   "2024-01-01,Iron 65,DemoLabs,sibutramine,weight loss,https://example.org/x\n")
    monkeypatch.setattr(tainted, "CSV_PATH", csv)
    tainted.reload()
    try:
        rep = _post(client, "iron", seed=7)["report"]
        assert rep["reputability"]["label"] == "severe"
        assert rep["verdict"] == "WARNING"
    finally:
        monkeypatch.undo()
        tainted.reload()


def test_label_only_scan(client):
    r = client.post("/scans?wait=true", json={"label": {"brand": "Nobody", "product_name": "Mystery Blend"}})
    rep = r.json()["report"]
    assert rep["accuracy"]["label"] == "not_measured"
    assert rep["verdict"] == "NO_REF"
