"""Adjudication: turning disagreed human labels into final labels,
with the record to prove it.

Rules (deterministic, in order):

  1. A case with no ratings at all is INCOMPLETE — it cannot be
     labelled, adjudicated or otherwise.
  2. A case whose present nominal labels are unanimous AND whose
     ordinal spread is at most 1 is AGREED: the final label is the
     unanimous label, the final quality is the lower median of the
     ordinal scores, and no adjudicator is involved.
  3. Every other case is DISAGREED and must carry an adjudicator
     decision (final label, final quality, rationale, adjudicator
     id). With one, the record is ADJUDICATED; without one it is
     INCOMPLETE — the pipeline refuses to invent a final label.
  4. Majority vote is recorded on every disagreed case as a
     diagnostic (what the crowd said, and whether the adjudicator
     followed it) — it never decides the final label by itself.

Escalation: when the dataset's nominal Krippendorff alpha falls
below the floor (default 0.667, Krippendorff's tentative-conclusion
threshold), the run is ESCALATED: thin agreements — exactly two
raters present with an ordinal spread of exactly 1 — are re-routed
to adjudication as well, because at that agreement level a two-rater
"agreement" is not evidence. Escalation is a property of the whole
run and is stamped on every record it produces.
"""

from __future__ import annotations

import statistics
from typing import Dict, List, Optional

from agreement import NOMINAL, krippendorff_alpha, units_from_cases

DEFAULT_ALPHA_FLOOR = 0.667


def majority_label(labels: List[str]) -> Optional[str]:
    """Strict majority label, or None on a tie / no labels."""
    if not labels:
        return None
    counts: Dict[str, int] = {}
    for lab in labels:
        counts[lab] = counts.get(lab, 0) + 1
    best = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    if list(counts.values()).count(best[1]) > 1:
        return None
    return best[0]


def _present(case: Dict, field: str) -> List:
    return [v for v in case[field].values() if v is not None]


def needs_adjudication(case: Dict, escalated: bool = False) -> bool:
    labels = _present(case, "nominal")
    scores = _present(case, "ordinal")
    if not labels:
        return False  # no ratings: INCOMPLETE, not adjudicable
    if len(set(labels)) > 1:
        return True
    if scores and (max(scores) - min(scores)) >= 2:
        return True
    if escalated and len(labels) == 2 and scores \
            and (max(scores) - min(scores)) == 1:
        return True  # thin agreement under escalation
    return False


def adjudicate_case(case: Dict, escalated: bool = False) -> Dict:
    labels = _present(case, "nominal")
    scores = _present(case, "ordinal")
    record = {
        "case_id": case["case_id"],
        "rater_nominal": dict(case["nominal"]),
        "rater_ordinal": dict(case["ordinal"]),
        "n_raters_present": len(labels),
        "majority_label": majority_label(labels),
        "escalated_run": escalated,
    }
    if not labels:
        record.update({"status": "INCOMPLETE", "final_label": None,
                       "final_quality": None, "adjudicator": None,
                       "rationale": None,
                       "reason": "no ratings present"})
        return record
    if not needs_adjudication(case, escalated=escalated):
        record.update({
            "status": "AGREED",
            "final_label": labels[0],
            "final_quality": int(statistics.median_low(scores)) if scores else None,
            "adjudicator": None,
            "rationale": "unanimous — no adjudication required",
            "reason": "unanimous nominal labels, ordinal spread <= 1",
        })
        return record
    adj = case.get("adjudicator")
    if not adj:
        record.update({"status": "INCOMPLETE", "final_label": None,
                       "final_quality": None, "adjudicator": None,
                       "rationale": None,
                       "reason": "disagreed case has no adjudicator decision"})
        return record
    record.update({
        "status": "ADJUDICATED",
        "final_label": adj["label"],
        "final_quality": adj["quality"],
        "adjudicator": adj["adjudicator"],
        "rationale": adj["rationale"],
        "reason": "adjudicator decision recorded",
        "adjudicator_followed_majority":
            record["majority_label"] is not None
            and adj["label"] == record["majority_label"],
    })
    return record


def adjudicate_dataset(dataset: Dict,
                       alpha_floor: float = DEFAULT_ALPHA_FLOOR) -> Dict:
    """Adjudicate every case; compute agreement + escalation first.

    Returns {alpha_nominal, alpha_ordinal, alpha_floor, escalated,
    records, counts} — the full adjudication report for one dataset.
    Alphas are rounded to 6 decimals for stable reporting.
    """
    cases = dataset["cases"]
    alpha_nom = krippendorff_alpha(units_from_cases(cases, "nominal"), NOMINAL)
    alpha_ord = krippendorff_alpha(units_from_cases(cases, "ordinal"), "ordinal",
                                   domain=[1, 2, 3, 4, 5])
    escalated = alpha_nom < alpha_floor
    records = [adjudicate_case(c, escalated=escalated) for c in cases]
    counts = {"AGREED": 0, "ADJUDICATED": 0, "INCOMPLETE": 0}
    for rec in records:
        counts[rec["status"]] += 1
    return {
        "dataset_id": dataset["dataset_id"],
        "alpha_nominal": round(alpha_nom, 6),
        "alpha_ordinal": round(alpha_ord, 6),
        "alpha_floor": alpha_floor,
        "escalated": escalated,
        "records": records,
        "counts": counts,
    }
