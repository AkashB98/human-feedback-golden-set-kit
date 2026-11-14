"""Shared builders for the test suite (not a test module)."""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import generate_dataset, generate_heldout  # noqa: E402

_ADJ = {"label": "fail", "quality": 2,
        "rationale": "Adjudicator rationale for the test case.",
        "adjudicator": "senior-reviewer-1"}


def make_case(case_id, nominal, ordinal, adjudicator=None,
              prompt=None, response=None):
    return {
        "case_id": case_id,
        "prompt": prompt or f"Prompt for {case_id}.",
        "response": response or f"Response for {case_id}.",
        "failure_class": "none",
        "pattern": "clear",
        "planted_truth": None,
        "nominal": dict(nominal),
        "ordinal": dict(ordinal),
        "adjudicator": adjudicator,
    }


def make_dataset(cases, dataset_id="synthetic-test"):
    return {"dataset_id": dataset_id, "seed": 0, "description": "test",
            "raters": ["R1", "R2", "R3", "R4"], "cases": cases}


def split_case(case_id, with_adjudicator=True):
    """A 2-2 nominal split — always disagreed."""
    return make_case(
        case_id,
        {"R1": "pass", "R2": "pass", "R3": "fail", "R4": "fail"},
        {"R1": 4, "R2": 4, "R3": 2, "R4": 2},
        adjudicator=copy.deepcopy(_ADJ) if with_adjudicator else None)


def unanimous_case(case_id, label="pass", score=4):
    return make_case(
        case_id,
        {r: label for r in ("R1", "R2", "R3", "R4")},
        {r: score for r in ("R1", "R2", "R3", "R4")})


def thin_case(case_id):
    """Exactly two raters present, nominal agreement, ordinal
    spread exactly 1: AGREED normally, re-routed under escalation."""
    return make_case(
        case_id,
        {"R1": "pass", "R2": "pass", "R3": None, "R4": None},
        {"R1": 4, "R2": 3, "R3": None, "R4": None})


def low_alpha_dataset():
    """Five split cases + one thin case: alpha is low, so the run
    escalates and the thin case (no adjudicator) goes INCOMPLETE."""
    cases = [split_case(f"L{i:03d}") for i in range(1, 6)]
    cases.append(thin_case("L006"))
    return make_dataset(cases, "synthetic-low-alpha")


def calm_dataset_with_thin():
    """Ten unanimous cases + one thin case: alpha stays high, no
    escalation, the thin case is AGREED."""
    cases = [unanimous_case(f"K{i:03d}") for i in range(1, 11)]
    cases.append(thin_case("K011"))
    return make_dataset(cases, "synthetic-calm")


def main_dataset():
    return generate_dataset()


def heldout_pool(clean=False):
    return generate_heldout(clean=clean)


def dataset_without_adjudicator(case_id="C010"):
    ds = generate_dataset()
    for case in ds["cases"]:
        if case["case_id"] == case_id:
            assert case["adjudicator"] is not None
            case["adjudicator"] = None
    return ds
