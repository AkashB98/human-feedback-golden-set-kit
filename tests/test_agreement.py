"""Krippendorff alpha correctness, including hand-computed cases.

The hand cases below were computed by hand from the coincidence
matrix definition BEFORE the implementation existed; the comments
show the arithmetic so a reader can re-derive every number.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agreement import (  # noqa: E402
    alpha_components, coincidence_matrix, krippendorff_alpha,
    units_from_cases,
)
from generator import generate_sanity  # noqa: E402

# Hand case 1 (nominal): units (1,1),(1,1),(2,2),(2,1),(1,2).
# Coincidence (m=2 per unit): o11=4, o22=2, o12=o21=2; n=10,
# marginals n1=6, n2=4. Do = o12+o21 = 4.
# De = 2 * (6*4/9) = 48/9. alpha = 1 - 4/(48/9) = 1 - 0.75 = 0.25.
HAND_NOMINAL = [[1, 1], [1, 1], [2, 2], [2, 1], [1, 2]]

# Hand case 2 (nominal, 3 raters): (1,1,1),(2,2,1),(2,2,2).
# o11=3, o22=1+3=4, o12=o21=1; n=9, marginals 4 and 5.
# Do = 2. De = 2 * (4*5/8) = 5. alpha = 1 - 2/5 = 0.6.
HAND_3RATER = [[1, 1, 1], [2, 2, 1], [2, 2, 2]]

# Hand case 3 (ordinal): (1,1),(2,2),(3,3),(1,2) over domain 1..3.
# o = diag(2,2,2) + o12=o21=1; n=8, marginals (3,3,2).
# Ordinal deltas: d12=(6-3)^2=9, d23=(5-2.5)^2=6.25,
# d13=(8-2.5)^2=30.25. Do = 2*9 = 18.
# De = 2*(9/7*9 + 6/7*6.25 + 6/7*30.25) = 600/7.
# alpha = 1 - 18/(600/7) = 1 - 0.21 = 0.79.
# Nominal on the same data: Do=2, De=2*(9/7+6/7+6/7)=6 -> 2/3.
HAND_ORDINAL = [[1, 1], [2, 2], [3, 3], [1, 2]]


class TestHandComputed(unittest.TestCase):
    def test_nominal_hand_case_quarter(self):
        self.assertAlmostEqual(
            krippendorff_alpha(HAND_NOMINAL, "nominal"), 0.25, places=12)

    def test_nominal_hand_case_three_raters(self):
        self.assertAlmostEqual(
            krippendorff_alpha(HAND_3RATER, "nominal"), 0.6, places=12)

    def test_ordinal_hand_case(self):
        self.assertAlmostEqual(
            krippendorff_alpha(HAND_ORDINAL, "ordinal", domain=[1, 2, 3]),
            0.79, places=12)

    def test_same_data_nominal_below_ordinal(self):
        # The single disagreement is a NEAR miss (1 vs 2): ordinal
        # alpha must exceed nominal alpha on identical data.
        nom = krippendorff_alpha(HAND_ORDINAL, "nominal")
        ordi = krippendorff_alpha(HAND_ORDINAL, "ordinal", domain=[1, 2, 3])
        self.assertAlmostEqual(nom, 2 / 3, places=12)
        self.assertGreater(ordi, nom)

    def test_coincidence_matrix_pinned(self):
        o, dom = coincidence_matrix(HAND_NOMINAL)
        self.assertEqual(dom, [1, 2])
        self.assertEqual(o, [[4.0, 2.0], [2.0, 2.0]])

    def test_components_pinned(self):
        comp = alpha_components(HAND_NOMINAL, "nominal")
        self.assertEqual(comp["marginals"], [6.0, 4.0])
        self.assertEqual(comp["n_pairable_values"], 10)
        self.assertAlmostEqual(comp["observed_disagreement"], 4.0, places=12)
        self.assertAlmostEqual(comp["expected_disagreement"], 48 / 9,
                               places=12)


class TestEdgeCases(unittest.TestCase):
    def test_perfect_agreement_is_one(self):
        units = [[1, 1], [2, 2], [1, 1], [2, 2, 2]]
        self.assertEqual(krippendorff_alpha(units, "nominal"), 1.0)
        self.assertEqual(
            krippendorff_alpha(units, "ordinal", domain=[1, 2]), 1.0)

    def test_single_value_domain_is_one_by_convention(self):
        # De == 0: chance disagreement is impossible.
        self.assertEqual(krippendorff_alpha([[1, 1], [1, 1]], "nominal"),
                         1.0)

    def test_no_pairable_ratings_raises(self):
        with self.assertRaises(ValueError):
            krippendorff_alpha([[1], [None, None], []], "nominal")
        with self.assertRaises(ValueError):
            krippendorff_alpha([], "nominal")

    def test_unknown_metric_raises(self):
        with self.assertRaises(ValueError):
            krippendorff_alpha(HAND_NOMINAL, "kappa")

    def test_value_outside_domain_raises(self):
        with self.assertRaises(ValueError):
            krippendorff_alpha([[1, 9]], "ordinal", domain=[1, 2, 3])


class TestMissingData(unittest.TestCase):
    def test_singletons_do_not_change_alpha(self):
        extended = HAND_NOMINAL + [[1], [None, None], [2], []]
        self.assertAlmostEqual(
            krippendorff_alpha(extended, "nominal"), 0.25, places=12)

    def test_missing_within_unit_uses_remaining_raters(self):
        # (1,1,None) behaves exactly like (1,1) for pairing.
        a = krippendorff_alpha([[1, 1, None], [2, 1, 2]], "nominal")
        b = krippendorff_alpha([[1, 1], [2, 1, 2]], "nominal")
        self.assertAlmostEqual(a, b, places=12)


class TestInvariances(unittest.TestCase):
    def test_rater_order_permutation_invariant(self):
        shuffled = [[u[1], u[0]] if len(u) == 2 else u
                    for u in HAND_NOMINAL]
        self.assertAlmostEqual(
            krippendorff_alpha(shuffled, "nominal"), 0.25, places=12)

    def test_nominal_relabel_invariant(self):
        relabelled = [[3 - v for v in u] for u in HAND_NOMINAL]
        self.assertAlmostEqual(
            krippendorff_alpha(relabelled, "nominal"), 0.25, places=12)

    def test_ordinal_extra_empty_domain_values_invariant(self):
        # Domain values nobody used carry zero marginal mass and
        # cannot change any ordinal distance.
        a = krippendorff_alpha(HAND_ORDINAL, "ordinal", domain=[1, 2, 3])
        b = krippendorff_alpha(HAND_ORDINAL, "ordinal",
                               domain=[1, 2, 3, 4, 5])
        self.assertAlmostEqual(a, b, places=12)

    def test_ordinal_far_miss_costs_more_than_near_miss(self):
        near = alpha_components(HAND_ORDINAL, "ordinal", domain=[1, 2, 3])
        far_units = [[1, 1], [2, 2], [3, 3], [1, 3]]
        far = alpha_components(far_units, "ordinal", domain=[1, 2, 3])
        self.assertGreater(far["observed_disagreement"],
                           near["observed_disagreement"])
        self.assertLess(far["alpha"], near["alpha"])


class TestSanitySets(unittest.TestCase):
    def test_perfect_sanity_alpha_is_one(self):
        ds = generate_sanity("perfect")
        self.assertEqual(
            krippendorff_alpha(units_from_cases(ds["cases"], "nominal"),
                               "nominal"), 1.0)
        self.assertEqual(
            krippendorff_alpha(units_from_cases(ds["cases"], "ordinal"),
                               "ordinal", domain=[1, 2, 3, 4, 5]), 1.0)

    def test_chance_sanity_alpha_near_zero(self):
        ds = generate_sanity("chance")
        nom = krippendorff_alpha(units_from_cases(ds["cases"], "nominal"),
                                 "nominal")
        ordi = krippendorff_alpha(units_from_cases(ds["cases"], "ordinal"),
                                  "ordinal", domain=[1, 2, 3, 4, 5])
        self.assertLess(abs(nom), 0.15)
        self.assertLess(abs(ordi), 0.15)

    def test_units_from_cases_sorted_rater_order(self):
        case = {"nominal": {"R2": "fail", "R1": "pass",
                            "R4": None, "R3": "pass"}}
        self.assertEqual(units_from_cases([case], "nominal"),
                         [["pass", "fail", "pass", None]])


if __name__ == "__main__":
    unittest.main()
