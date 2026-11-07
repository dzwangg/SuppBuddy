"""Reputability = what do public records say about this brand/product? No sensor input.

Evidence dict shape (built in pipeline.py stage 2):
  tainted: list[{product_name, company, hidden_ingredients, date, url, match_score}]
  recalls: list[{classification, reason_for_recall, recall_number, report_date, product_description, code_info}]
  caers:   {total, serious, sample_size, top_reactions: [[term, count]]} | None
  dsld:    {found, dsld_id, product_name, brand, mismatches: [...]} | None

TODO(calibrate): point weights are judgment calls. Keep them simple and explainable on stage.
"""
from __future__ import annotations

from datetime import date

from app.schemas import LabelInfo, ReputabilityScore

BASE = 70
CLASS_POINTS = {"CLASS I": 35, "CLASS II": 20, "CLASS III": 8}
# openFDA lists one record per size/SKU and keeps recalls forever. Counting every record at full
# weight scored Nature Made 0/100 over 2013-2016 recalls. So: one penalty per recall event,
# weighted by age, capped. A lot-number match is always added in full.
MAX_RECALL_PENALTY = 40


def _age_weight(report_date: str | None) -> float:
    try:
        d = date(int(report_date[:4]), int(report_date[4:6]), int(report_date[6:8]))
    except (TypeError, ValueError):
        return 1.0
    years = (date.today() - d).days / 365.25
    return 1.0 if years <= 2 else 0.5 if years <= 5 else 0.1


def score_reputability(evidence: dict | None, label: LabelInfo | None) -> ReputabilityScore:
    if not evidence or all(evidence.get(k) is None for k in ("tainted", "recalls", "caers", "dsld")):
        return ReputabilityScore(label="unknown", findings=[{"type": "info", "text": "No public records checked."}])

    score, findings, severe = BASE, [], False

    for hit in evidence.get("tainted") or []:
        if hit.get("match_type") == "company":
            score -= 25
            findings.append({
                "type": "tainted_company", "severity": "medium",
                "text": f"Same company ({hit.get('company')}) appears on the FDA tainted-supplement list for "
                        f"a different product, '{hit.get('product_name')}' (hidden {hit.get('hidden_ingredients')}).",
                "url": hit.get("url"),
            })
            continue
        severe = True
        findings.append({
            "type": "tainted", "severity": "high",
            "text": f"FDA tainted-supplement list: '{hit.get('product_name')}' by {hit.get('company')} "
                    f"contained hidden {hit.get('hidden_ingredients') or 'drug ingredients'}.",
            "url": hit.get("url"),
        })

    lot = (label.lot or "").strip().lower() if label else ""
    events: dict = {}
    for r in evidence.get("recalls") or []:
        events.setdefault(r.get("event_id") or (r.get("recalling_firm"), r.get("report_date")), []).append(r)
    recall_penalty, lot_penalty = 0.0, 0
    for recs in events.values():
        classes = [(r.get("classification") or "").upper() for r in recs]
        cls = min(classes, key=lambda c: list(CLASS_POINTS).index(c) if c in CLASS_POINTS else 9)
        first = recs[0]
        weight = _age_weight(first.get("report_date"))
        lot_hit = bool(lot) and any(lot in (r.get("code_info") or "").lower() for r in recs)
        recall_penalty += CLASS_POINTS.get(cls, 10) * weight
        if lot_hit:
            lot_penalty += 30
            severe = severe or cls == "CLASS I"
        severity = "high" if lot_hit or (cls == "CLASS I" and weight == 1.0) else "medium" if weight >= 0.5 else "low"
        count = f", {len(recs)} products" if len(recs) > 1 else ""
        findings.append({
            "type": "recall", "severity": severity,
            "text": f"{cls.title() or 'Recall'} ({first.get('report_date', '?')}{count}, {first.get('recalling_firm', '?')}): "
                    f"{(first.get('reason_for_recall') or '')[:200]}"
                    + (" YOUR LOT NUMBER APPEARS IN THIS RECALL." if lot_hit else ""),
            "recall_number": first.get("recall_number"),
        })
    score -= round(min(recall_penalty, MAX_RECALL_PENALTY)) + lot_penalty

    caers = evidence.get("caers")
    if caers and caers.get("total"):
        total, serious = caers["total"], caers.get("serious", 0)
        # Counts, not rates: popular brands get more reports, so this barely moves the score.
        if serious >= 25:
            score -= 5
        findings.append({
            "type": "adverse_events", "severity": "low",
            "text": f"{total} FDA adverse-event reports mention this brand "
                    f"({serious} serious in the {caers.get('sample_size', 0)} most recent). "
                    "Reports are unverified and not proof the product caused harm.",
            "top_reactions": caers.get("top_reactions", [])[:5],
        })

    dsld = evidence.get("dsld")
    if dsld and dsld.get("barcode_owner_mismatch"):
        # The barcode on this bottle is registered to a different product: relabeled or counterfeit.
        score -= 30
        findings.append({"type": "barcode_mismatch", "severity": "high", "text": dsld["barcode_owner_mismatch"],
                         "url": f"https://dsld.od.nih.gov/label/{dsld.get('dsld_id')}"})
    if dsld:
        if dsld.get("found"):
            score += 5
            findings.append({"type": "label_registry", "severity": "info",
                             "text": f"Label is registered in the NIH Dietary Supplement Label Database "
                                     f"(id {dsld.get('dsld_id')})."})
            for m in dsld.get("mismatches", []):
                score -= 5
                findings.append({"type": "label_mismatch", "severity": "medium", "text": m})
        else:
            findings.append({"type": "label_registry", "severity": "low",
                             "text": "Could not find this product in the NIH label database."})

    # TODO(verify-api): certifications on the label are self-reported. Verify against USP/NSF
    # public listings before giving credit. For now, credit is small and flagged as unverified.
    if label and label.certifications:
        score += 3
        findings.append({"type": "certification", "severity": "info",
                         "text": f"Label claims: {', '.join(label.certifications)} (not yet verified)."})

    checked = [k for k in ("tainted", "recalls", "caers", "dsld") if evidence.get(k) is not None]
    if not any(f.get("severity") in ("high", "medium") for f in findings):
        findings.append({"type": "info", "severity": "info",
                         "text": f"No red flags in sources checked ({', '.join(checked)}). "
                                 "Absence of records is not proof of quality."})

    score = max(0, min(100, score))
    if severe:
        lbl = "severe"
    elif score >= 75:
        lbl = "trusted"
    elif score >= 50:
        lbl = "mixed"
    else:
        lbl = "concerning"
    return ReputabilityScore(label=lbl, score=score, findings=findings)
