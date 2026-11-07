"""Reputability = what do public records say about this brand/product? No sensor input.

Evidence dict shape (built in pipeline.py stage 2):
  tainted: list[{product_name, company, hidden_ingredients, date, url, match_score}]
  recalls: list[{classification, reason_for_recall, recall_number, report_date, product_description, code_info}]
  caers:   {total, serious, sample_size, top_reactions: [[term, count]]} | None
  dsld:    {found, dsld_id, product_name, brand, mismatches: [...]} | None

TODO(calibrate): point weights are judgment calls. Keep them simple and explainable on stage.
"""
from __future__ import annotations

from app.schemas import LabelInfo, ReputabilityScore

BASE = 70


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
    for r in evidence.get("recalls") or []:
        cls = (r.get("classification") or "").upper()
        pts = {"CLASS I": 35, "CLASS II": 20, "CLASS III": 8}.get(cls, 10)
        lot_hit = bool(lot) and lot in (r.get("code_info") or "").lower()
        if lot_hit:
            pts += 30
            severe = severe or cls == "CLASS I"
        score -= pts
        findings.append({
            "type": "recall", "severity": "high" if lot_hit or cls == "CLASS I" else "medium",
            "text": f"{cls.title() or 'Recall'} ({r.get('report_date', '?')}): {r.get('reason_for_recall', '')[:200]}"
                    + (" YOUR LOT NUMBER APPEARS IN THIS RECALL." if lot_hit else ""),
            "recall_number": r.get("recall_number"),
        })

    caers = evidence.get("caers")
    if caers and caers.get("total"):
        total, serious = caers["total"], caers.get("serious", 0)
        # Counts, not rates: reporting is sparse and popular brands get more reports.
        if serious >= 25:
            score -= 15
        elif serious >= 5:
            score -= 7
        findings.append({
            "type": "adverse_events", "severity": "medium" if serious >= 5 else "low",
            "text": f"{total} FDA adverse-event reports mention this brand "
                    f"({serious} serious in the {caers.get('sample_size', 0)} most recent). "
                    "Reports are unverified and not proof the product caused harm.",
            "top_reactions": caers.get("top_reactions", [])[:5],
        })

    dsld = evidence.get("dsld")
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
