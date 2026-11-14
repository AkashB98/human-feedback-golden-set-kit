"""Adjudication rules, escalation, and the pinned main-dataset
report."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adjudication import (  # noqa: E402
    adjudicate_case, adjudicate_dataset, majority_label,
    needs_adjudication,
)
from helpers import (  # noqa: E402
    calm_dataset_with_thin, low_alpha_dataset, main_dataset, make_case,
    split_case, thin_case, unanimous_case,
)


class TestMajority(unittest.TestCase):
    def test_strict_majority(self):
        self.assertEqual(majority_label(["pass", "pass", "fail"]), "pass")

    def test_tie_is_none(self):
        self.assertIsNone(majority_label(["pass", "fail"]))
        self.assertIsNone(majority_label(["pass", "pass", "fail", "fail"]))

    def test_empty_is_none(self):
        self.assertIsNone(majority_label([]))


class TestCaseRules(unittest.TestCase):
    def test_unanimous_agreed_with_lower_median(self):
        case = make_case("T001",
                         {r: "pass" for r in ("R1", "R2", "R3", "R4")},
                         {"R1": 4, "R2": 5, "R3": 4, "R4": 5})
        rec = adjudicate_case(case)
        self.assertEqual(rec["status"], "AGREED")
        self.assertEqual(rec["final_label"], "pass")
        self.assertEqual(rec["final_quality"], 4)  # median_low of 4,5,4,5
        self.assertIsNone(rec["adjudicator"])

    def test_split_with_adjudicator(self):
        rec = adjudicate_case(split_case("T002"))
        self.assertEqual(rec["status"], "ADJUDICATED")
        self.assertEqual(rec["final_label"], "fail")
        self.assertEqual(rec["adjudicator"], "senior-reviewer-1")
        self.assertTrue(rec["rationale"])
        self.assertIsNone(rec["majority_label"])  # 2-2 tie

    def test_majority_followed_flag(self):
        case = make_case(
            "T003",
            {"R1": "pass", "R2": "pass", "R3": "pass", "R4": "fail"},
            {"R1": 4, "R2": 4, "R3": 4, "R4": 2},
            adjudicator={"label": "pass", "quality": 4,
                         "rationale": "Majority was right.",
                         "adjudicator": "senior-reviewer-1"})
        rec = adjudicate_case(case)
        self.assertEqual(rec["status"], "ADJUDICATED")
        self.assertTrue(rec["adjudicator_followed_majority"])

    def test_split_without_adjudicator_incomplete(self):
        rec = adjudicate_case(split_case("T004", with_adjudicator=False))
        self.assertEqual(rec["status"], "INCOMPLETE")
        self.assertIsNone(rec["final_label"])

    def test_no_ratings_incomplete(self):
        case = make_case("T005",
                         {r: None for r in ("R1", "R2", "R3", "R4")},
                         {r: None for r in ("R1", "R2", "R3", "R4")})
        rec = adjudicate_case(case)
        self.assertEqual(rec["status"], "INCOMPLETE")
        self.assertIn("no ratings", rec["reason"])

    def test_ordinal_spread_two_needs_adjudication(self):
        case = make_case("T006",
                         {r: "pass" for r in ("R1", "R2", "R3", "R4")},
                         {"R1": 5, "R2": 5, "R3": 3, "R4": 5})
        self.assertTrue(needs_adjudication(case))
        self.assertEqual(adjudicate_case(case)["status"], "INCOMPLETE")

    def test_ordinal_spread_one_is_agreed(self):
        case = make_case("T007",
                         {r: "pass" for r in ("R1", "R2", "R3", "R4")},
                         {"R1": 4, "R2": 4, "R3": 3, "R4": 4})
        self.assertFalse(needs_adjudication(case))
        self.assertEqual(adjudicate_case(case)["status"], "AGREED")


class TestEscalation(unittest.TestCase):
    def test_thin_case_agreed_when_calm(self):
        report = adjudicate_dataset(calm_dataset_with_thin())
        self.assertFalse(report["escalated"])
        thin = next(r for r in report["records"]
                    if r["case_id"] == "K011")
        self.assertEqual(thin["status"], "AGREED")

    def test_low_alpha_escalates_and_reroutes_thin_case(self):
        report = adjudicate_dataset(low_alpha_dataset())
        self.assertTrue(report["escalated"])
        self.assertLess(report["alpha_nominal"], report["alpha_floor"])
        thin = next(r for r in report["records"]
                    if r["case_id"] == "L006")
        self.assertEqual(thin["status"], "INCOMPLETE")
        self.assertTrue(thin["escalated_run"])
        # The genuinely split cases still adjudicate fine.
        self.assertEqual(report["counts"]["ADJUDICATED"], 5)


class TestMainDatasetPinned(unittest.TestCase):
    def test_counts_and_alphas_pinned(self):
        report = adjudicate_dataset(main_dataset())
        self.assertEqual(report["alpha_nominal"], 0.685802)
        self.assertEqual(report["alpha_ordinal"], 0.895938)
        self.assertFalse(report["escalated"])
        self.assertEqual(report["counts"],
                         {"AGREED": 25, "ADJUDICATED": 11, "INCOMPLETE": 0})

    def test_every_adjudicated_record_has_rationale(self):
        report = adjudicate_dataset(main_dataset())
        for rec in report["records"]:
            if rec["status"] == "ADJUDICATED":
                self.assertTrue(rec["rationale"])
                self.assertEqual(rec["adjudicator"], "senior-reviewer-1")


if __name__ == "__main__":
    unittest.main()
