"""Regression tests for the 2026-11-07 fixes (forced tool_choice 400s, recall scoring, barcode check, LCD)."""
import asyncio
from datetime import date, timedelta
from types import SimpleNamespace as NS

from app import vision
from app.agent import harness
from app.evidence import dsld
from app.schemas import LabelInfo
from app.scoring.reputability import score_reputability
from app.scoring.verdict import lcd_message


def _ymd(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).strftime("%Y%m%d")


class Recorder:
    """Fake messages API that records every call and replies from a script."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    async def create(self, **kw):
        self.calls.append({**kw, "messages": list(kw.get("messages", []))})  # snapshot: the harness appends later
        return self.replies.pop(0)

    async def parse(self, **kw):
        self.calls.append(kw)
        return self.replies.pop(0)


SUBMIT = NS(type="tool_use", id="s", name="submit_report",
            input={"headline": "h", "summary": "s", "key_findings": [], "advice": [], "citations": []})


def test_agent_asks_instead_of_forcing_tool_choice(monkeypatch):
    fake = Recorder([NS(stop_reason="end_turn", content=[NS(type="text", text="All done.")]),
                     NS(stop_reason="tool_use", content=[SUBMIT])])
    monkeypatch.setattr(harness, "client", lambda: NS(messages=fake))
    assert asyncio.run(harness.run_agent({}))["headline"] == "h"
    assert len(fake.calls) == 2 and all("tool_choice" not in c for c in fake.calls)
    assert fake.calls[1]["messages"][-1]["content"].startswith("Now call submit_report")


def test_agent_gives_up_cleanly(monkeypatch):
    silent = NS(stop_reason="end_turn", content=[NS(type="text", text="...")])
    fake = Recorder([silent, silent])
    monkeypatch.setattr(harness, "client", lambda: NS(messages=fake))
    try:
        asyncio.run(harness.run_agent({}))
        raise AssertionError("should raise so the pipeline keeps the deterministic report")
    except RuntimeError:
        pass
    assert len(fake.calls) == 2 and all("tool_choice" not in c for c in fake.calls)


def test_vision_uses_structured_output(monkeypatch):
    fake = Recorder([NS(stop_reason="end_turn", parsed_output=LabelInfo(brand="Acme", product_name="B2"))])
    monkeypatch.setattr(vision, "client", lambda: NS(messages=fake))
    label = asyncio.run(vision.extract_label([(b"jpg", "image/jpeg")]))
    assert label.brand == "Acme"
    assert fake.calls[0]["output_format"] is LabelInfo and "tool_choice" not in fake.calls[0]
    assert fake.calls[0]["output_config"] == {"effort": "low"}


def _rep(recalls=None, caers=None, dsld_ev=None, label=None):
    return score_reputability({"tainted": None, "recalls": recalls or [], "caers": caers, "dsld": dsld_ev}, label)


def test_old_sku_level_recalls_dont_sink_a_big_brand():
    # Shape of Nature Made's real openFDA data: one 2016 event listed once per bottle size.
    recs = [{"event_id": "75000", "classification": "Class II", "report_date": "20160914",
             "recalling_firm": "Pharmavite", "reason_for_recall": "superpotent"} for _ in range(12)]
    rep = _rep(recs, caers={"total": 497, "serious": 34, "sample_size": 100})
    assert rep.label == "mixed" and rep.score >= 55
    assert sum(f["type"] == "recall" for f in rep.findings) == 1  # one event, not 12


def test_recent_class_one_recall_still_counts():
    rep = _rep([{"event_id": "1", "classification": "Class I", "report_date": _ymd(100),
                 "recalling_firm": "Acme", "reason_for_recall": "Salmonella"}])
    assert rep.label == "concerning"


def test_lot_number_in_class_one_recall_is_severe():
    rep = _rep([{"event_id": "1", "classification": "Class I", "report_date": _ymd(3000), "recalling_firm": "Acme",
                 "reason_for_recall": "lead", "code_info": "Lots 4417A, 4418B"}], label=LabelInfo(lot="4417A"))
    assert rep.label == "severe"


def test_barcode_registered_to_another_brand(monkeypatch):
    async def search(q, size=10):
        assert q == '"7 00580 72363 3"'
        return [{"dsld_id": "174894", "off_market": 1, "entry_date": "2018-03-23"},
                {"dsld_id": "211102", "off_market": 0, "entry_date": "2020-01-25"}]

    async def get_label(dsld_id):
        return {"dsld_id": dsld_id, "brand": "Seeking Health", "product_name": "Riboflavin 400 mg",
                "upc": "7 00580 72363 3", "ingredients": []}

    monkeypatch.setattr(dsld, "search", search)
    monkeypatch.setattr(dsld, "get_label", get_label)
    photo = LabelInfo(brand="Brightroot Labs", product_name="Riboflavin 100 mg", upc="0700580723633")
    ev = asyncio.run(dsld.lookup(photo))
    assert ev["dsld_id"] == "211102" and "Seeking Health" in ev["barcode_owner_mismatch"]  # on-market version
    assert _rep(dsld_ev=ev, label=photo).label == "concerning"

    same = asyncio.run(dsld.lookup(LabelInfo(brand="Seeking Health", product_name="Riboflavin", upc="700580723633")))
    assert same["found"] and "barcode_owner_mismatch" not in same


def test_name_match_needs_the_same_brand(monkeypatch):
    async def search(q, size=10):
        return [{"dsld_id": "304843", "brand": "Some Other Co", "product_name": "Riboflavin 100 mg"}]

    monkeypatch.setattr(dsld, "search", search)
    ev = asyncio.run(dsld.lookup(LabelInfo(brand="Brightroot Labs", product_name="Riboflavin 100 mg")))
    assert ev["found"] is False


def test_upc_format():
    assert dsld.upc_format("0700580723633") == "7 00580 72363 3"
    assert dsld.upc_format("000000000000") is None
    assert dsld.upc_format("123") is None


def test_lcd_text():
    report = {"verdict": "CONSISTENT", "reputability": {"score": 100}}
    assert lcd_message("complete", report).line1.strip() == "CONSISTENT R100"
    assert lcd_message("error", None).code == "ERROR"


def test_empty_tainted_list_is_not_a_checked_source(client):
    rep = client.post("/scans?wait=true", json={"label": {"brand": "Nobody", "product_name": "Mystery"}}).json()
    assert rep["report"]["reputability"]["label"] == "unknown"
    assert rep["stages"]["deterministic"]["tainted"].startswith("skipped")
