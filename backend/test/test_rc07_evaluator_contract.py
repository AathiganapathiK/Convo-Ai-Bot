"""
RC-07 - the benchmark evaluator's multi-table dimension contract.

The ratified RC-07 ruling says the resolver may select ONE physical copy of a
business dimension that is replicated across tables, and should normally select
the copy on the resolved metric's table. `Division` is the live example: same
business name, same synonyms, same GROUPING role, confirmed on all three
tables, and the identical ten values on each.

`evaluate_v2` used to require the resolver to return EVERY physical copy an
expectation listed, which is the opposite of that ruling and made a correct
answer unrepresentable. These tests pin the corrected contract and, just as
importantly, pin the three things it must still reject.

Pure unit tests over the comparison helpers - no database, no resolver.

    python -m unittest backend.test.test_rc07_evaluator_contract
"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.join(HERE, "semantic_benchmark", "v2")

_spec = importlib.util.spec_from_file_location(
    "evaluate_v2_under_test", os.path.join(V2, "evaluate_v2.py")
)
evaluate_v2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evaluate_v2)

SALES = "QB_MDJMD_SALES_5YRS_SUMMARY"
OUTSTANDING = "PBI_OUTSTANDING_ENES_SUMMARY"
ORDER_PENDING = "PBI_ENES_ORDER_PENDING_SUMMARY"


def entry(business_name, physical, ambiguous=None):
    if ambiguous is None:
        ambiguous = len(physical) > 1
    return {
        "business_name": business_name,
        "resolved": True,
        "physical": [{"table_name": t, "column_name": c} for t, c in physical],
        "ambiguous_across_tables": ambiguous,
    }


def actual(*pairs):
    return {(t.strip().lower(), c.strip().lower()) for t, c in pairs}


DIVISION_REPLICAS = entry("Division", [
    (SALES, "Division"),
    (OUTSTANDING, "Division"),
    (ORDER_PENDING, "Division"),
])
CATEGORY_REPLICAS = entry("Category", [
    (SALES, "Category"),
    (ORDER_PENDING, "Category"),
])
CITY_ONLY = entry("City", [(OUTSTANDING, "City")])


class TestReplicaAcceptance(unittest.TestCase):
    """A replicated dimension is satisfied by any one of its physical copies."""

    def test_1_three_division_replicas_sales_actual_passes(self):
        self.assertTrue(evaluate_v2._identity_satisfied(
            [DIVISION_REPLICAS], actual((SALES, "Division"))))

    def test_2_three_division_replicas_outstanding_actual_passes(self):
        self.assertTrue(evaluate_v2._identity_satisfied(
            [DIVISION_REPLICAS], actual((OUTSTANDING, "Division"))))

    def test_2b_three_division_replicas_order_pending_actual_passes(self):
        # Affinity follows the metric: "Show quantity for VT" resolves Qty on
        # Order Pending, so this copy must be acceptable too.
        self.assertTrue(evaluate_v2._identity_satisfied(
            [DIVISION_REPLICAS], actual((ORDER_PENDING, "Division"))))


class TestRejections(unittest.TestCase):
    """The contract must stay strict about everything except the replica set."""

    def test_3_division_expected_btype_actual_fails(self):
        # btype is a different dimension with 55 values that merely happens to
        # contain "VT". Table affinity must never bridge these.
        self.assertFalse(evaluate_v2._identity_satisfied(
            [DIVISION_REPLICAS], actual((OUTSTANDING, "btype"))))

    def test_4_city_expected_district_actual_fails(self):
        self.assertFalse(evaluate_v2._identity_satisfied(
            [CITY_ONLY], actual((OUTSTANDING, "District"))))

    def test_5_empty_actual_fails(self):
        self.assertFalse(evaluate_v2._identity_satisfied([DIVISION_REPLICAS], set()))
        self.assertFalse(evaluate_v2._identity_satisfied([CITY_ONLY], set()))

    def test_5b_empty_expectation_requires_empty_actual(self):
        self.assertTrue(evaluate_v2._identity_satisfied([], set()))
        self.assertFalse(evaluate_v2._identity_satisfied(
            [], actual((OUTSTANDING, "District"))))

    def test_two_copies_of_one_replicated_dimension_fails(self):
        # Selecting one copy is the point; returning two is not "any subset".
        self.assertFalse(evaluate_v2._identity_satisfied(
            [DIVISION_REPLICAS],
            actual((SALES, "Division"), (OUTSTANDING, "Division"))))

    def test_extra_unexpected_dimension_fails(self):
        self.assertFalse(evaluate_v2._identity_satisfied(
            [DIVISION_REPLICAS],
            actual((SALES, "Division"), (OUTSTANDING, "City"))))

    def test_missing_one_of_two_expected_dimensions_fails(self):
        self.assertFalse(evaluate_v2._identity_satisfied(
            [DIVISION_REPLICAS, CITY_ONLY], actual((SALES, "Division"))))

    def test_two_expected_dimensions_both_present_passes(self):
        self.assertTrue(evaluate_v2._identity_satisfied(
            [DIVISION_REPLICAS, CITY_ONLY],
            actual((SALES, "Division"), (OUTSTANDING, "City"))))


class TestSingleTableUnchanged(unittest.TestCase):
    """Test 8 - a single-table expectation behaves exactly as equality did."""

    def test_8_exact_single_table_match_passes(self):
        self.assertTrue(evaluate_v2._identity_satisfied(
            [CITY_ONLY], actual((OUTSTANDING, "City"))))

    def test_8b_single_table_wrong_table_fails(self):
        self.assertFalse(evaluate_v2._identity_satisfied(
            [CITY_ONLY], actual((SALES, "City"))))

    def test_8c_single_table_wrong_column_fails(self):
        self.assertFalse(evaluate_v2._identity_satisfied(
            [CITY_ONLY], actual((OUTSTANDING, "Category"))))

    def test_8d_metrics_are_never_replicated_so_equality_still_governs(self):
        metric = entry("C Y", [(SALES, "CY")])
        self.assertTrue(evaluate_v2._identity_satisfied(
            [metric], actual((SALES, "CY"))))
        self.assertFalse(evaluate_v2._identity_satisfied(
            [metric], actual((OUTSTANDING, "billamt"))))


class TestValueDeduplication(unittest.TestCase):

    def test_6_replica_duplicates_collapse(self):
        self.assertEqual(evaluate_v2._distinct(["vt", "vt", "vt"]), ["vt"])
        self.assertEqual(evaluate_v2._distinct(["vt"]), ["vt"])

    def test_6b_comparison_is_symmetric(self):
        self.assertEqual(evaluate_v2._distinct(["vt", "vt", "vt"]),
                         evaluate_v2._distinct(["vt"]))

    def test_7_genuinely_different_values_remain_distinct(self):
        self.assertEqual(
            evaluate_v2._distinct(["chennai", "coimbatore"]),
            ["chennai", "coimbatore"])
        self.assertNotEqual(
            evaluate_v2._distinct(["chennai", "coimbatore"]),
            evaluate_v2._distinct(["chennai"]))

    def test_7b_marketing_is_not_collapsed_into_a_different_category(self):
        self.assertNotEqual(
            evaluate_v2._distinct(["marketing"]),
            evaluate_v2._distinct(["marketing", "others"]))

    def test_7c_empty_stays_empty(self):
        self.assertEqual(evaluate_v2._distinct([]), [])
        self.assertEqual(evaluate_v2._distinct(None), [])
        self.assertNotEqual(evaluate_v2._distinct([]), evaluate_v2._distinct(["vt"]))


class TestNamedBenchmarkCases(unittest.TestCase):
    """
    The six cases the RC-07 ruling names, expressed as the identity shapes the
    live datasets actually hold. Each asserts the contract decision only - the
    end-to-end pass/fail also depends on value, ambiguity and retrieval, which
    this change does not touch.
    """

    def test_e1_063_and_e1_170_vt_division(self):
        # "Show sales for VT division" / "Now show sales for VT division".
        # Metric is Sales.CY, so the resolver returns Sales.Division.
        self.assertTrue(evaluate_v2._identity_satisfied(
            [DIVISION_REPLICAS], actual((SALES, "Division"))))

    def test_e1_097_and_e1_098_bare_vt_expect_no_dimension(self):
        # "Show sales for VT" / "Total sales for VT" name no dimension, and the
        # resolver returns none. The contract must accept empty-vs-empty, and
        # these cases must still fail on ambiguity status elsewhere.
        self.assertTrue(evaluate_v2._identity_satisfied([], set()))

    def test_e1_097_value_multiplicity_is_no_longer_a_value_failure(self):
        self.assertEqual(evaluate_v2._distinct(["vt", "vt", "vt", "vt"]),
                         evaluate_v2._distinct(["vt"]))

    def test_e1_126_vt_divisions_plural(self):
        self.assertTrue(evaluate_v2._identity_satisfied(
            [entry("Division", [(SALES, "Division")])],
            actual((SALES, "Division"))))

    def test_e1_145_marketin_category(self):
        self.assertTrue(evaluate_v2._identity_satisfied(
            [entry("Category", [(SALES, "Category")])],
            actual((SALES, "Category"))))

    def test_e1_145_would_still_fail_on_the_wrong_category_copy_being_extra(self):
        self.assertFalse(evaluate_v2._identity_satisfied(
            [CATEGORY_REPLICAS],
            actual((SALES, "Category"), (ORDER_PENDING, "Category"))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
