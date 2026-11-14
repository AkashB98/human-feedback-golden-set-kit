"""Golden-set export and the audit trail.

The golden set is the exportable artifact: every case that reached
a final label (AGREED or ADJUDICATED), carrying its provenance —
the rater labels, whether an adjudicator decided it, who, and why.
INCOMPLETE cases are never exported; they are listed separately so
the gap is visible instead of silent.

The audit trail is the adjudication report's records verbatim: one
entry per case, in case order, so any final label can be traced
back to the exact ratings and rationale that produced it.
"""

from __future__ import annotations

from typing import Dict, List

from adjudication import adjudicate_dataset
from leakage import find_leakage, internal_duplicates


def build_golden_set(dataset: Dict, report: Dict = None) -> List[Dict]:
    """Golden cases from an adjudication report (computed if not
    given). Sorted by case_id; deterministic."""
    if report is None:
        report = adjudicate_dataset(dataset)
    by_id = {c["case_id"]: c for c in dataset["cases"]}
    golden: List[Dict] = []
    for rec in report["records"]:
        if rec["status"] == "INCOMPLETE":
            continue
        case = by_id[rec["case_id"]]
        golden.append({
            "case_id": rec["case_id"],
            "prompt": case["prompt"],
            "response": case["response"],
            "failure_class": case["failure_class"],
            "final_label": rec["final_label"],
            "final_quality": rec["final_quality"],
            "provenance": {
                "source_dataset": dataset["dataset_id"],
                "status": rec["status"],
                "rater_nominal": rec["rater_nominal"],
                "rater_ordinal": rec["rater_ordinal"],
                "adjudicator": rec["adjudicator"],
                "rationale": rec["rationale"],
            },
        })
    golden.sort(key=lambda g: g["case_id"])
    return golden


def build_audit_trail(report: Dict) -> List[Dict]:
    """The audit trail: adjudication records, one per case."""
    return list(report["records"])


def incomplete_case_ids(report: Dict) -> List[str]:
    return [r["case_id"] for r in report["records"]
            if r["status"] == "INCOMPLETE"]


def build_export(dataset: Dict, heldout: Dict = None,
                 threshold: float = 0.5) -> Dict:
    """Full export bundle: adjudication summary, golden set, audit
    trail, and (when a held-out pool is given) the leakage check of
    the golden set against that pool plus the golden set's internal
    duplicate check."""
    report = adjudicate_dataset(dataset)
    golden = build_golden_set(dataset, report)
    export = {
        "dataset_id": dataset["dataset_id"],
        "alpha_nominal": report["alpha_nominal"],
        "alpha_ordinal": report["alpha_ordinal"],
        "alpha_floor": report["alpha_floor"],
        "escalated": report["escalated"],
        "counts": report["counts"],
        "incomplete_case_ids": incomplete_case_ids(report),
        "golden_set": golden,
        "audit_trail": build_audit_trail(report),
        "internal_duplicates": internal_duplicates(golden,
                                                   threshold=threshold),
        "leakage": None,
    }
    if heldout is not None:
        export["leakage"] = find_leakage(golden, heldout["items"],
                                         threshold=threshold)
    return export
