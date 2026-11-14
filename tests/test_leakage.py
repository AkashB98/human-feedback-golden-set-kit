"""N-gram Jaccard leakage check: unit behaviour + the planted
near-duplicates in the seeded pool."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from golden import build_golden_set  # noqa: E402
from leakage import (  # noqa: E402
    find_leakage, internal_duplicates, jaccard, shingles, text_similarity,
    tokenize,
)
from helpers import heldout_pool, main_dataset  # noqa: E402


class TestPrimitives(unittest.TestCase):
    def test_tokenize_lowercase_alphanumeric(self):
        self.assertEqual(tokenize("Hello, LD-4114! It's $42.00."),
                         ["hello", "ld", "4114", "it", "s", "42", "00"])

    def test_identical_text_similarity_one(self):
        text = "the agent confirmed the refund on monday morning"
        self.assertEqual(text_similarity(text, text), 1.0)

    def test_disjoint_text_similarity_zero(self):
        a = "alpha bravo charlie delta echo foxtrot"
        b = "zebra yodel xray whisky victor uniform"
        self.assertEqual(text_similarity(a, b), 0.0)

    def test_short_text_fallback_shingle(self):
        self.assertEqual(shingles("only two"), frozenset({("only", "two")}))
        self.assertEqual(text_similarity("only two", "only two"), 1.0)
        self.assertEqual(text_similarity("only two", "only three"), 0.0)

    def test_jaccard_empty_conventions(self):
        self.assertEqual(jaccard(frozenset(), frozenset()), 1.0)
        self.assertEqual(jaccard(frozenset({1}), frozenset()), 0.0)


class TestPlantedLeakage(unittest.TestCase):
    def setUp(self):
        self.golden = build_golden_set(main_dataset())

    def test_planted_pool_flags_exactly_two_pairs(self):
        flags = find_leakage(self.golden, heldout_pool()["items"])
        pairs = {(f["golden_case_id"], f["heldout_case_id"])
                 for f in flags}
        self.assertEqual(pairs, {("C003", "H009"), ("C012", "H010")})

    def test_planted_jaccards_pinned(self):
        flags = find_leakage(self.golden, heldout_pool()["items"])
        by_pair = {(f["golden_case_id"], f["heldout_case_id"]): f["jaccard"]
                   for f in flags}
        self.assertEqual(by_pair[("C003", "H009")], 0.803571)
        self.assertEqual(by_pair[("C012", "H010")], 0.804348)

    def test_clean_pool_flags_nothing(self):
        self.assertEqual(
            find_leakage(self.golden, heldout_pool(clean=True)["items"]), [])

    def test_golden_set_has_no_internal_duplicates(self):
        self.assertEqual(internal_duplicates(self.golden), [])

    def test_threshold_below_max_distinct_pair(self):
        # The most similar DISTINCT golden pair sits below the 0.5
        # default but above 0.4: the threshold is what separates
        # "same archetype, different case" from "near-duplicate".
        flags = find_leakage(self.golden, heldout_pool()["items"],
                             threshold=0.4)
        self.assertGreater(len(flags), 2)

    def test_flags_sorted_by_descending_similarity(self):
        flags = find_leakage(self.golden, heldout_pool()["items"],
                             threshold=0.4)
        sims = [f["jaccard"] for f in flags]
        self.assertEqual(sims, sorted(sims, reverse=True))

    def test_internal_duplicates_detects_crafted_pair(self):
        cases = [
            {"case_id": "X1", "prompt": "please reset my password now",
             "response": "open settings and choose reset password today"},
            {"case_id": "X2", "prompt": "please reset my password now",
             "response": "open settings and choose reset password today"},
            {"case_id": "X3", "prompt": "where is my parcel delivery",
             "response": "the courier arrives on thursday evening"},
        ]
        flags = internal_duplicates(cases)
        self.assertEqual(len(flags), 1)
        self.assertEqual((flags[0]["case_id_a"], flags[0]["case_id_b"]),
                         ("X1", "X2"))
        self.assertEqual(flags[0]["jaccard"], 1.0)


if __name__ == "__main__":
    unittest.main()
