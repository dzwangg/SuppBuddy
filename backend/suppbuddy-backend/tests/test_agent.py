"""Exercise the tool-use loop with a fake Claude client (no API key, no network)."""
import asyncio
from types import SimpleNamespace as NS

from app.agent import harness


class FakeMessages:
    def __init__(self):
        self.calls = 0

    async def create(self, **kw):
        self.calls += 1
        if self.calls == 1:  # first turn: ask for crowd stats
            return NS(stop_reason="tool_use", content=[
                NS(type="text", text="Checking crowd data."),
                NS(type="tool_use", id="t1", name="crowd_stats",
                   input={"brand": "DemoLabs", "product_name": "Vitamin C 1000"}),
            ])
        # second turn: tool_result must have been sent back
        last = kw["messages"][-1]["content"]
        assert last[0]["type"] == "tool_result" and last[0]["tool_use_id"] == "t1"
        return NS(stop_reason="tool_use", content=[
            NS(type="tool_use", id="t2", name="submit_report", input={
                "headline": "Looks normal", "summary": "Fine.", "key_findings": ["a"],
                "advice": ["b"], "citations": [{"source": "openFDA"}]}),
        ])


def test_agent_loop(monkeypatch):
    fake = NS(messages=FakeMessages())
    monkeypatch.setattr(harness, "client", lambda: fake)
    out = asyncio.run(harness.run_agent({"label": {"brand": "DemoLabs"}}))
    assert out["headline"] == "Looks normal"
    assert fake.messages.calls == 2
