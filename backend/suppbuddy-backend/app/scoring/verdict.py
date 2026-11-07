"""Combine the three scores into one verdict + deterministic report + LCD message.

The LLM never changes the verdict or scores. It only writes prose on top (see agent/harness.py).
That keeps the demo stable and the judging story honest.
"""
from __future__ import annotations

from app.schemas import (AccuracyScore, Citation, LcdMessage, QualityScore, Report, ReputabilityScore,
                         Verdict)


def decide(acc: AccuracyScore, qual: QualityScore, rep: ReputabilityScore, qc_ok: bool | None) -> Verdict:
    if rep.label == "severe" or acc.label == "inconsistent":
        return Verdict.WARNING
    if qc_ok is False and rep.label in ("unknown", "trusted", "mixed"):
        return Verdict.BAD_SCAN
    if acc.label == "borderline" or qual.label == "poor" or rep.label == "concerning":
        return Verdict.CHECK
    if acc.label == "consistent" and rep.label in ("trusted", "mixed", "unknown"):
        return Verdict.CHECK if qual.label == "poor" else Verdict.CONSISTENT
    if acc.label in ("insufficient_data", "not_measured"):
        return Verdict.NO_REF  # concerning/severe records already returned above
    return Verdict.CHECK


HEADLINES = {
    Verdict.CONSISTENT: "Matches what we expect for this product",
    Verdict.CHECK: "Some things worth a closer look",
    Verdict.WARNING: "Red flags found",
    Verdict.NO_REF: "Not enough reference data yet",
    Verdict.BAD_SCAN: "Scan didn't work, please retest",
}


def build_report(verdict: Verdict, acc: AccuracyScore, qual: QualityScore, rep: ReputabilityScore,
                 product_name: str | None, qc: dict | None, citations: list[Citation]) -> Report:
    findings: list[str] = []
    if acc.note:
        findings.append(acc.note)
    for d in acc.top_deviations[:2]:
        if "z" in d and abs(d["z"]) > 1.5:
            findings.append(f"{d['feature']} is {d['z']:+.1f} std from the product's norm.")
        elif "expected_range" in d:
            findings.append(f"{d['feature']}={d['value']} outside expected {d['expected_range']}.")
    findings += qual.issues[:3]
    findings += [f["text"] for f in rep.findings if f.get("severity") in ("high", "medium")][:4]
    if qc and qc.get("flags"):
        findings.insert(0, "Scan problems: " + "; ".join(qc["flags"]))

    advice = {
        Verdict.CONSISTENT: ["Keep the bottle; scan again if a new batch looks or smells different."],
        Verdict.CHECK: ["Re-run the test with a fresh sample to rule out prep error.",
                        "Check the lot number against the manufacturer's site."],
        Verdict.WARNING: ["Stop taking it until you've checked with a pharmacist or doctor.",
                          "Report the product to the FDA (MedWatch / Safety Reporting Portal)."],
        Verdict.NO_REF: ["Confirm this scan so it becomes a reference for the next person."],
        Verdict.BAD_SCAN: ["Re-blank with clean water, check the cuvette is seated, and retry."],
    }[verdict]

    name = product_name or "this product"
    summary = (
        f"Sensor check: {acc.label.replace('_', ' ')}. Quality: {qual.label}. "
        f"Public records: {rep.label}" + (f" ({rep.score}/100)" if rep.score is not None else "") + f" for {name}."
    )
    if acc.reference_synthetic:
        summary += " Reference data includes simulated demo scans."

    return Report(
        verdict=verdict, headline=HEADLINES[verdict], summary=summary,
        accuracy=acc, quality=qual, reputability=rep,
        key_findings=findings, advice=advice, citations=citations,
    )


def lcd_message(status: str, report: dict | None, width: int = 16) -> LcdMessage:
    """TODO(lcd): width/lines assume a 16x2 character LCD. Trevor: change to match the panel."""
    def fit(s: str) -> str:
        return s[:width].ljust(width)

    if status in ("pending",) or not report:
        return LcdMessage(code="TESTING", line1=fit("SuppBuddy"), line2=fit("Analyzing..."))
    v = report["verdict"]
    line2 = {
        "CONSISTENT": "Looks consistent",
        "CHECK": "Check phone",
        "WARNING": "WARNING: see app",
        "NO_REF": "Need more data",
        "BAD_SCAN": "Retest sample",
    }.get(v, "See phone")
    score = report.get("reputability", {}).get("score")
    line1 = f"{v[:9]}" + (f" R{score}" if score is not None else "")
    return LcdMessage(code=v, line1=fit(line1), line2=fit(line2))
