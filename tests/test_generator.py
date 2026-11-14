"""Generator determinism, planted patterns, and fixture shape."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adjudication import needs_adjudication  # noqa: E402
from generator import (  # noqa: E402
    generate_dataset, generate_heldout, generate_sanity,
)


class TestDeterminism(unittest.TestCase):
    def test_dataset_deterministic(self):
        self.assertEqual(generate_dataset(), generate_dataset())

    def test_heldout_deterministic(self):
        self.assertEqual(generate_heldout(), generate_heldout())
        self.assertEqual(generate_heldout(clean=True),
                         generate_heldout(clean=True))

    def test_sanity_deterministic(self):
        self.assertEqual(generate_sanity("perfect"),
                         generate_sanity("perfect"))
        self.assertEqual(generate_sanity("chance"), generate_sanity("chance"))

    def test_seed_changes_output(self):
        self.assertNotEqual(generate_dataset(seed=42),
                            generate_dataset(seed=7))


class TestShape(unittest.TestCase):
    def test_main_shape(self):
        ds = generate_dataset()
        self.assertEqual(len(ds["cases"]), 36)
        self.assertEqual(ds["raters"], ["R1", "R2", "R3", "R4"])
        for case in ds["cases"]:
            self.assertEqual(set(case["nominal"]), set(ds["raters"]))
            self.assertEqual(set(case["ordinal"]), set(ds["raters"]))

    def test_heldout_shape(self):
        pool = generate_heldout()
        self.assertEqual(len(pool["items"]), 10)
        origins = [i["origin"] for i in pool["items"]]
        self.assertEqual(sum(1 for o in origins
                             if o.startswith("near_duplicate_of")), 2)
        self.assertEqual(len(generate_heldout(clean=True)["items"]), 8)

    def test_sanity_shapes(self):
        self.assertEqual(len(generate_sanity("perfect")["cases"]), 12)
        self.assertEqual(len(generate_sanity("chance")["cases"]), 40)


class TestPlantedPatterns(unittest.TestCase):
    def test_missing_ratings_planted(self):
        ds = generate_dataset()
        missing = sum(1 for c in ds["cases"]
                      for v in c["nominal"].values() if v is None)
        self.assertEqual(missing, 10)
        # The planted R4 block: cases at index 28-30 (C029-C031).
        for idx in (28, 29, 30):
            self.assertIsNone(ds["cases"][idx]["nominal"]["R4"])
            self.assertIsNone(ds["cases"][idx]["ordinal"]["R4"])

    def test_every_case_pairable(self):
        for case in generate_dataset()["cases"]:
            present = [v for v in case["nominal"].values()
                       if v is not None]
            self.assertGreaterEqual(len(present), 2)

    def test_special_patterns_present(self):
        patterns = [c["pattern"] for c in generate_dataset()["cases"]]
        self.assertEqual(patterns.count("tone_split"), 3)
        self.assertEqual(patterns.count("leniency_split"), 3)
        self.assertEqual(patterns.count("clear"), 30)

    def test_adjudicator_attached_exactly_when_disagreed(self):
        for case in generate_dataset()["cases"]:
            self.assertEqual(case["adjudicator"] is not None,
                             needs_adjudication(case),
                             case["case_id"])

    def test_perfect_sanity_unanimous(self):
        for case in generate_sanity("perfect")["cases"]:
            self.assertEqual(len(set(case["nominal"].values())), 1)
            self.assertEqual(len(set(case["ordinal"].values())), 1)


if __name__ == "__main__":
    unittest.main()
