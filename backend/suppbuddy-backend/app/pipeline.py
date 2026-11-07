"""Scan research pipeline. Mirrors Peel's staged design: every stage is isolated, and a failure
downgrades to `skipped`/`unavailable` instead of killing the scan.

  pending --(stage 0-2, ~1-3 s)--> partial --(stage 3 agent, ~15-45 s)--> complete

Stage 0  QC + features         (local)
Stage 1  product resolution    (local + NIH DSLD)
Stage 2  deterministic scoring (local tainted CSV, openFDA recalls + CAERS, crowd fingerprint)
Stage 3  agent narrative       (Claude, optional)
"""
from __future__ import annotations

import asyncio
import logging
import time

from app import llm
from app.agent.harness import run_agent
from app.config import settings
from app.db import Scan, session
from app.evidence import dsld, openfda, tainted
from app.evidence.cache import OfflineMiss
from app.fingerprints import fingerprint_stats, get_fingerprint, get_or_create_product
from app.schemas import Citation, DeviceReadings, LabelInfo, Report, Verdict
from app.scoring.accuracy import score_accuracy
from app.scoring.quality import score_quality
from app.scoring.reputability import score_reputability
from app.scoring.verdict import build_report, decide
from app.sensors.features import extract_features

log = logging.getLogger("suppbuddy.pipeline")
_running: dict[str, asyncio.Task] = {}


def _patch(scan_id: str, stage: tuple[str, dict] | None = None, **fields) -> None:
    with session() as s:
        scan = s.get(Scan, scan_id)
        for k, v in fields.items():
            setattr(scan, k, v)
        if stage:
            scan.stages = {**(scan.stages or {}), stage[0]: stage[1]}
        scan.revision = (scan.revision or 0) + 1


async def _guard(coro, timeout: float):
    """Run a lookup; return (value, status) where status is ok|timeout|error|skipped."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout), "ok"
    except OfflineMiss:
        return None, "skipped (offline, not cached)"
    except asyncio.TimeoutError:
        return None, "timeout"
    except Exception as e:  # noqa: BLE001
        log.warning("lookup failed: %s", e)
        return None, f"error: {type(e).__name__}"


def _citations(evidence: dict) -> list[Citation]:
    cites: list[Citation] = []
    d = evidence.get("dsld") or {}
    if d.get("found"):
        cites.append(Citation(source="NIH Dietary Supplement Label Database", title=d.get("product_name"),
                              url=f"https://dsld.od.nih.gov/label/{d['dsld_id']}"))
    if evidence.get("recalls"):
        cites.append(Citation(source="openFDA food enforcement (recalls)",
                              url="https://open.fda.gov/apis/food/enforcement/"))
    if (evidence.get("caers") or {}).get("total"):
        cites.append(Citation(source="openFDA CAERS adverse event reports", url="https://open.fda.gov/apis/food/event/"))
    for t in evidence.get("tainted") or []:
        cites.append(Citation(source="FDA Tainted Products Marketed as Dietary Supplements",
                              title=t.get("product_name"), url=t.get("url") or None))
    return cites


async def run_scan(scan_id: str) -> None:
    t0 = time.monotonic()
    with session() as s:
        scan = s.get(Scan, scan_id)
        label = LabelInfo.model_validate(scan.label) if scan.label else None
        readings = DeviceReadings.model_validate(scan.readings) if scan.readings else None
        product_id = scan.product_id
        synthetic = scan.synthetic

    # ---- Stage 0: features ------------------------------------------------
    features, qc = None, None
    if readings:
        try:
            fr = extract_features(readings)
            features = fr.features if fr.ok else (fr.features or None)
            qc = {**fr.qc_dict(), "series": fr.series}
            _patch(scan_id, ("features", {"status": "ok" if fr.ok else "qc_failed"}), features=features, qc=qc)
        except Exception as e:  # noqa: BLE001
            log.exception("feature extraction failed")
            qc = {"ok": False, "flags": [f"feature_error: {e}"], "warnings": []}
            _patch(scan_id, ("features", {"status": "error", "error": str(e)}), qc=qc)
    else:
        _patch(scan_id, ("features", {"status": "skipped", "reason": "no readings"}))

    # ---- Stage 1: product -------------------------------------------------
    with session() as s:
        if not product_id and label:
            p = get_or_create_product(s, label.brand, label.product_name, label.model_dump())
            product_id = p.id if p else None
    _patch(scan_id, ("product", {"status": "ok" if product_id else "unknown"}), product_id=product_id)

    # ---- Stage 2: deterministic evidence + scores -------------------------
    evidence: dict = {"tainted": None, "recalls": None, "caers": None, "dsld": None}
    stage2: dict = {}
    if label:
        evidence["tainted"] = tainted.lookup(label.product_name, label.brand)
        stage2["tainted"] = f"ok ({tainted.status()['rows']} rows loaded)"
        (rec, st_r), (cae, st_c), (ds, st_d) = await asyncio.gather(
            _guard(openfda.recalls(label.brand, label.product_name), settings.http_timeout_s + 2),
            _guard(openfda.caers(label.brand), settings.http_timeout_s + 2),
            _guard(dsld.lookup(label), settings.http_timeout_s * 2 + 2),
        )
        evidence.update(recalls=rec, caers=cae, dsld=ds)
        stage2.update(recalls=st_r, caers=st_c, dsld=st_d)

    fp_stats, fp_n, fp_syn = None, 0, False
    if product_id:
        with session() as s:
            fp = get_fingerprint(s, product_id, readings.protocol if readings else None)
            if fp:
                fp_stats, fp_n, fp_syn = fingerprint_stats(fp), fp.n, fp.synthetic

    acc = score_accuracy(features if (qc or {}).get("ok") else None, fp_stats, fp_n, fp_syn, label)
    qual = score_quality(features if (qc or {}).get("ok") else None, qc, fp_stats)
    rep = score_reputability(evidence, label)
    verdict = decide(acc, qual, rep, (qc or {}).get("ok") if readings else None)
    report = build_report(verdict, acc, qual, rep, label.product_name if label else None, qc, _citations(evidence))
    _patch(scan_id, ("deterministic", {"status": "ok", **stage2, "elapsed_s": round(time.monotonic() - t0, 2)}),
           evidence=evidence, report=report.model_dump(mode="json"), status="partial")

    # ---- Stage 3: agent narrative -----------------------------------------
    if not llm.available() or verdict == Verdict.BAD_SCAN:
        reason = "no ANTHROPIC_API_KEY" if not llm.available() else "bad scan"
        _patch(scan_id, ("agent", {"status": "skipped", "reason": reason}), status="complete")
        return
    context = {
        "label": label.model_dump() if label else None,
        "sensor_features": features,
        "qc": {k: v for k, v in (qc or {}).items() if k != "series"},
        "crowd_fingerprint": {"n": fp_n, "synthetic": fp_syn, "stats": fp_stats},
        "deterministic_report": report.model_dump(mode="json"),
        "evidence_pack": evidence,
    }
    try:
        narrative = await run_agent(context)
        merged = report.model_copy(update={
            "headline": narrative.get("headline") or report.headline,
            "summary": narrative.get("summary") or report.summary,
            "key_findings": narrative.get("key_findings") or report.key_findings,
            "advice": narrative.get("advice") or report.advice,
            "citations": report.citations + [Citation.model_validate(c) for c in narrative.get("citations", [])],
            "generated_by": "agent",
        })
        _patch(scan_id, ("agent", {"status": "ok", "elapsed_s": round(time.monotonic() - t0, 2)}),
               report=Report.model_validate(merged.model_dump()).model_dump(mode="json"), status="complete")
    except Exception as e:  # noqa: BLE001
        log.warning("agent failed: %s", e)
        _patch(scan_id, ("agent", {"status": "unavailable", "error": f"{type(e).__name__}: {e}"[:300]}),
               status="complete")


def start(scan_id: str) -> None:
    """Fire-and-forget. Keeps a reference so the task isn't garbage-collected."""
    old = _running.get(scan_id)
    if old and not old.done():
        old.cancel()
    task = asyncio.create_task(_run_safely(scan_id))
    _running[scan_id] = task
    task.add_done_callback(lambda _: _running.pop(scan_id, None))


async def _run_safely(scan_id: str) -> None:
    try:
        await run_scan(scan_id)
    except Exception as e:  # noqa: BLE001
        log.exception("pipeline crashed")
        _patch(scan_id, ("pipeline", {"status": "error", "error": str(e)[:300]}), status="error")
