"""Regression tests for the 2026-11-07 adversarial review fixes: non-finite readings, input bounds, the API
token, the agent narrative merge, citation URLs, pipeline lifecycle and openFDA error text."""
import asyncio
import copy
import json
from dataclasses import replace
from types import SimpleNamespace as NS

import httpx
import pytest

from app import main as main_mod
from app import pipeline, sim
from app.agent import harness
from app.config import settings
from app.db import Scan, session
from app.evidence import openfda
from app.schemas import Citation


def _body(profile="vitamin_c", seed=1, label=None):
    # deep copy: sim.generate shares its DARK/BLANK dicts and PROFILES labels, and tests below mutate the body
    return copy.deepcopy({"label": label or sim.PROFILES[profile]["label"], "readings": sim.generate(profile, seed=seed),
                          "synthetic": True})


def _post_raw(client, body):  # json.dumps emits NaN/Infinity tokens; TestClient's json= refuses them
    return client.post("/scans?wait=true", content=json.dumps(body), headers={"content-type": "application/json"})


# ---- non-finite readings ---------------------------------------------------------------------
def test_nan_or_infinite_reading_is_rejected_at_the_api(client):
    body = _body()
    body["readings"]["samples"][5]["r"] = float("nan")
    assert _post_raw(client, body).status_code == 422
    body = _body()
    body["readings"]["dark"]["scatter"] = float("inf")
    assert _post_raw(client, body).status_code == 422


def test_computed_nan_fails_qc_instead_of_breaking_the_scan(client):
    body = _body("creatine")  # clear sample: no scatter fit, so the NaN below reaches the feature vector
    for s in body["readings"]["samples"]:
        s["t_ms"] = 0  # every dt is 0, so the slope is NaN
    r = client.post("/scans?wait=true", json=body)  # was a 500, and the scan stayed unreadable
    assert r.status_code == 202, r.text
    scan = r.json()
    assert scan["report"]["verdict"] == "BAD_SCAN" and scan["features"] is None
    assert any("non_finite" in f for f in scan["qc"]["flags"])
    assert client.get(f"/scans/{scan['id']}").status_code == 200
    assert client.post(f"/scans/{scan['id']}/confirm").status_code == 422  # never reaches the crowd reference


# ---- bounds at the trust boundary ------------------------------------------------------------
def test_oversized_or_empty_inputs_are_rejected(client):
    body = _body()
    body["label"]["claims"] = ["x" * 40000]
    assert client.post("/scans?wait=true", json=body).status_code == 422
    body = _body()
    body["readings"]["device_id"] = "d" * 1000
    assert client.post("/scans?wait=true", json=body).status_code == 422
    body = _body()
    body["readings"]["blank"] = {}
    assert client.post("/scans?wait=true", json=body).status_code == 422


def test_label_photo_upload_size_is_capped(client, monkeypatch):
    monkeypatch.setattr(main_mod.llm, "available", lambda: True)
    r = client.post("/label/extract", files={"images": ("a.jpg", b"x" * 9_000_000, "image/jpeg")})
    assert r.status_code == 413


# ---- API token --------------------------------------------------------------------------------
def test_api_token_is_required_when_set(client, monkeypatch):
    monkeypatch.setattr(main_mod, "settings", replace(settings, api_token="hunter2"))
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer hunter2"}).status_code == 200


# ---- agent harness ----------------------------------------------------------------------------
class Recorder:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    async def create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        return self.replies.pop(0)


def _submit(**inp):
    return NS(type="tool_use", id="s", name="submit_report", input=inp)


@pytest.mark.parametrize("stop", ["max_tokens", "refusal"])
def test_cut_off_or_refused_submit_is_not_a_report(monkeypatch, stop):
    fake = Recorder([NS(stop_reason=stop, content=[_submit(headline="Looks fi")])])
    monkeypatch.setattr(harness, "client", lambda: NS(messages=fake))
    with pytest.raises(RuntimeError):
        asyncio.run(harness.run_agent({}))


def test_submit_report_schema_is_strict():
    from app.agent.tools import SUBMIT_REPORT
    assert SUBMIT_REPORT["strict"] is True
    assert SUBMIT_REPORT["input_schema"]["additionalProperties"] is False
    assert SUBMIT_REPORT["input_schema"]["properties"]["citations"]["items"]["additionalProperties"] is False


def test_verdict_comes_first_in_the_agent_context(client, monkeypatch):
    seen = {}

    async def fake_agent(context):
        seen["keys"] = list(context)
        return {"headline": "ok", "summary": "s", "key_findings": [], "advice": [], "citations": []}

    monkeypatch.setattr(pipeline, "run_agent", fake_agent)
    monkeypatch.setattr(pipeline.llm, "available", lambda: True)
    label = dict(sim.PROFILES["vitamin_c"]["label"])
    label["claims"] = ["c" * 300] * 40  # the biggest label the API now accepts
    scan = client.post("/scans?wait=true", json=_body(label=label)).json()
    assert seen["keys"][0] == "deterministic_report"
    assert scan["report"]["generated_by"] == "agent"


def test_agent_adds_to_the_measured_text_and_bad_citations_are_dropped(client, monkeypatch):
    body = _body("vitamin_c_cornstarch", seed=43, label=sim.PROFILES["vitamin_c"]["label"])
    monkeypatch.setattr(pipeline.llm, "available", lambda: False)
    det = client.post("/scans?wait=true", json=body).json()["report"]

    async def fake_agent(context):
        return {"headline": "Verified pure and safe to take", "summary": "x" * 5000,
                "key_findings": ["agent finding"] * 20, "advice": ["Keep taking it as directed."] * 5,
                "citations": [{"source": "FDA", "url": "javascript:alert(1)"}, {"source": "ok", "url": "https://fda.gov/x"},
                              {"title": "no source"}, "garbage", None, {"source": "num", "url": 7}]}

    monkeypatch.setattr(pipeline, "run_agent", fake_agent)
    monkeypatch.setattr(pipeline.llm, "available", lambda: True)
    rep = client.post("/scans?wait=true", json=body).json()["report"]
    assert rep["generated_by"] == "agent" and rep["verdict"] == det["verdict"]
    assert rep["headline"] == "Verified pure and safe to take"  # the verdict title sits above it in the app
    assert len(rep["summary"]) == 800
    assert rep["advice"][:len(det["advice"])] == det["advice"] and len(rep["advice"]) <= len(det["advice"]) + 2
    assert rep["key_findings"][:len(det["key_findings"])] == det["key_findings"]
    added = rep["citations"][len(det["citations"]):]
    assert [c["source"] for c in added] == ["FDA", "ok", "num"]
    assert [c["url"] for c in added] == [None, "https://fda.gov/x", None]


def test_citation_urls_are_web_only():
    assert Citation(source="s", url="tel:+1900").url is None
    assert Citation(source="s", url="file:///etc/passwd").url is None
    assert Citation(source="s", url="not a url").url is None
    assert Citation(source="s", url=" https://open.fda.gov/x ").url == "https://open.fda.gov/x"


# ---- pipeline lifecycle -----------------------------------------------------------------------
def test_start_twice_keeps_the_live_task(monkeypatch):
    async def slow(scan_id):
        await asyncio.sleep(10)

    monkeypatch.setattr(pipeline, "_run_safely", slow)

    async def main():
        pipeline.start("twice")
        first = pipeline._running["twice"]
        pipeline.start("twice")
        second = pipeline._running["twice"]
        await asyncio.sleep(0.01)  # the cancelled first task finishes and runs its callback
        assert first.cancelled() and pipeline._running.get("twice") is second  # was: popped by first's callback
        second.cancel()
        await asyncio.sleep(0.01)
        assert "twice" not in pipeline._running

    asyncio.run(main())


def test_restart_settles_scans_left_mid_run(client):
    with session() as s:
        s.add(Scan(id="stale-pending", status="pending", revision=0, stages={}))
        s.add(Scan(id="stale-partial", status="partial", revision=0, stages={}, report={"verdict": "CHECK"}))
    assert pipeline.sweep_stale() == 2
    assert client.get("/scans/stale-pending").json()["status"] == "error"
    partial = client.get("/scans/stale-partial").json()
    assert partial["status"] == "complete" and partial["lcd"]["code"] == "CHECK"  # the measured verdict survives


def test_shutdown_cancel_settles_a_running_scan(client, monkeypatch):
    with session() as s:
        s.add(Scan(id="live", status="partial", revision=0, stages={}, report={"verdict": "CHECK"}))

    async def hang(scan_id):
        await asyncio.sleep(10)

    monkeypatch.setattr(pipeline, "run_scan", hang)

    async def main():
        pipeline.start("live")
        await asyncio.sleep(0)
        pipeline._running["live"].cancel()
        await asyncio.sleep(0.01)

    asyncio.run(main())
    assert client.get("/scans/live").json()["status"] == "complete"


# ---- openFDA ----------------------------------------------------------------------------------
def test_openfda_error_does_not_echo_the_api_key(monkeypatch):
    monkeypatch.setattr(openfda, "settings", replace(settings, openfda_api_key="sk-SECRET-123"))

    def handler(request):
        assert "sk-SECRET-123" in str(request.url)  # still sent, as before; it just must not come back
        return httpx.Response(500, text="boom")

    real = httpx.AsyncClient
    monkeypatch.setattr(openfda.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(RuntimeError) as e:
        asyncio.run(openfda._get("/food/enforcement.json", "x", 1))
    assert "sk-SECRET-123" not in str(e.value) and "500" in str(e.value)
