"""Golden-set export, provenance, and the audit trail."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adjudication import adjudicate_dataset  # noqa: E402
from golden import (  # noqa: E402
    build_audit_trail, build_export, build_golden_set,
    incomplete_case_ids,
)
from helpers import (  # noqa: E402
    dataset_without_adjudicator, heldout_pool, main_dataset,
)


class TestGoldenSet(unittest.TestCase):
    def setUp(self):
        self.dataset = main_dataset()
        self.golden = build_golden_set(self.dataset)

    def test_all_cases_exported_when_complete(self):
        self.assertEqual(len(self.golden), 36)

    def test_sorted_by_case_id(self):
        ids = [g["case_id"] for g in self.golden]
        self.assertEqual(ids, sorted(ids))

    def test_provenance_complete(self):
        for entry in self.golden:
            self.assertIn(entry["final_label"], ("pass", "fail"))
            self.assertIsInstance(entry["final_quality"], int)
            prov = entry["provenance"]
            self.assertEqual(prov["source_dataset"],
                             self.dataset["dataset_id"])
            self.assertEqual(set(prov["rater_nominal"]),
                             {"R1", "R2", "R3", "R4"})
            if prov["status"] == "ADJUDICATED":
                self.assertEqual(prov["adjudicator"], "senior-reviewer-1")
                self.assertTrue(prov["rationale"])
            else:
                self.assertEqual(prov["status"], "AGREED")
                self.assertIn("unanimous", prov["rationale"])

    def test_final_labels_match_adjudication_records(self):
        report = adjudicate_dataset(self.dataset)
        by_id = {r["case_id"]: r for r in report["records"]}
        for entry in self.golden:
            rec = by_id[entry["case_id"]]
            self.assertEqual(entry["final_label"], rec["final_label"])
            self.assertEqual(entry["final_quality"], rec["final_quality"])

    def test_no_planted_truth_in_export(self):
        for entry in self.golden:
            self.assertNotIn("planted_truth", entry)
            self.assertNotIn("planted_truth", entry["provenance"])


class TestIncompleteHandling(unittest.TestCase):
    def test_incomplete_case_excluded_and_listed(self):
        ds = dataset_without_adjudicator("C010")
        export = build_export(ds)
        self.assertEqual(export["incomplete_case_ids"], ["C010"])
        self.assertEqual(len(export["golden_set"]), 35)
        self.assertNotIn("C010",
                         [g["case_id"] for g in export["golden_set"]])
        # The audit trail still carries the case — the gap is visible.
        trail_ids = [r["case_id"] for r in export["audit_trail"]]
        self.assertIn("C010", trail_ids)


class TestAuditTrailAndExport(unittest.TestCase):
    def test_audit_trail_covers_every_case_in_order(self):
        ds = main_dataset()
        report = adjudicate_dataset(ds)
        trail = build_audit_trail(report)
        self.assertEqual([r["case_id"] for r in trail],
                         [c["case_id"] for c in ds["cases"]])

    def test_export_without_heldout_has_no_leakage(self):
        export = build_export(main_dataset())
        self.assertIsNone(export["leakage"])
        self.assertEqual(export["internal_duplicates"], [])

    def test_export_with_heldout_reports_leakage(self):
        export = build_export(main_dataset(), heldout_pool())
        self.assertEqual(len(export["leakage"]), 2)
        self.assertEqual(export["counts"]["INCOMPLETE"], 0)
        self.assertFalse(export["escalated"])

    def test_incomplete_ids_empty_on_main(self):
        report = adjudicate_dataset(main_dataset())
        self.assertEqual(incomplete_case_ids(report), [])


if __name__ == "__main__":
    unittest.main()
