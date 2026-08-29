"""
Gate 5 / Gate 6 accuracy fixes.

Each test here corresponds to a false positive or false negative found during
the end-to-end verification. Written before the fixes, so every one of them
failed first.

The file is organised so that each fix is proved in both directions: the wrong
SQL or answer is caught, AND the legitimate variant still passes. A fix that
removes a false positive by creating a false negative is not a fix.
"""

import os
import sys
import unittest
from decimal import Decimal

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.guard import verify_sql_against_plan
from ai.guard.grounding import verify_answer_against_results
from ai.guard.models import Severity, ViolationCode
from ai.guard.numbers import extract_numeric_claims

from semantic.models.semantic_plan import (
    FilterOperator,
    RankDirection,
    RankMeasure,
    SemanticDimension,
    SemanticFilter,
    SemanticIntent,
    SemanticMetric,
    SemanticPlan,
    SemanticRanking,
)

T = "QB_MDJMD_SALES_5YRS_SUMMARY"
RUPEE = "₹"


def M(col="cy", agg="SUM"):
    return SemanticMetric(
        metric_name=col, business_name="Sales", table_name=T,
        column_name=col, aggregation_type=agg,
    )


def D(col="state1"):
    return SemanticDimension(
        dimension_name=col, business_name=col, table_name=T, column_name=col,
    )


def F(col="state1", values=None, op=FilterOperator.EQUAL):
    return SemanticFilter(
        dimension_name=col, table_name=T, column_name=col,
        operator=op, values=values or ["Tamil Nadu"],
    )


PLAN_FILTER = SemanticPlan(
    intent=SemanticIntent.AGGREGATE, metrics=[M()], filters=[F()], primary_table=T,
)
PLAN_PLAIN = SemanticPlan(metrics=[M()], primary_table=T)
PLAN_GROUP = SemanticPlan(metrics=[M()], dimensions=[D()], primary_table=T)
PLAN_RANK = SemanticPlan(
    metrics=[M()], dimensions=[D()],
    ranking=SemanticRanking(top_n=5, direction=RankDirection.DESC,
                            measure=RankMeasure.ABSOLUTE),
    primary_table=T,
)


def sev(plan, sql):
    return verify_sql_against_plan(plan, sql).severity


def codes(plan, sql):
    return verify_sql_against_plan(plan, sql).codes()


# ===========================================================================
# GATE 5 - A. Wrapped aggregates (was a FALSE POSITIVE)
# ===========================================================================

class TestWrappedAggregates(unittest.TestCase):
    """
    SUM(CAST(cy ...)) is still SUM of cy. Value-preserving wrappers must not
    read as a different metric - but arithmetic inside the aggregate genuinely
    is a different quantity and must still be caught.
    """

    def test_cast_wrapper_passes(self):
        self.assertEqual(
            sev(PLAN_FILTER,
                f"SELECT SUM(CAST(cy AS DECIMAL(18,2))) FROM {T} "
                "WHERE state1='Tamil Nadu'"),
            Severity.PASS,
        )

    def test_isnull_wrapper_passes(self):
        self.assertEqual(
            sev(PLAN_FILTER,
                f"SELECT SUM(ISNULL(cy,0)) FROM {T} WHERE state1='Tamil Nadu'"),
            Severity.PASS,
        )

    def test_coalesce_wrapper_passes(self):
        self.assertEqual(
            sev(PLAN_FILTER,
                f"SELECT SUM(COALESCE(cy,0)) FROM {T} WHERE state1='Tamil Nadu'"),
            Severity.PASS,
        )

    def test_nested_wrappers_pass(self):
        self.assertEqual(
            sev(PLAN_FILTER,
                f"SELECT SUM(ROUND(ISNULL(cy,0),2)) FROM {T} "
                "WHERE state1='Tamil Nadu'"),
            Severity.PASS,
        )

    def test_wrapped_wrong_metric_still_caught(self):
        """The fix must not make any wrapper acceptable regardless of column."""

        self.assertIn(
            ViolationCode.METRIC_MISMATCH.value,
            codes(PLAN_FILTER,
                  f"SELECT SUM(CAST(py AS DECIMAL(18,2))) FROM {T} "
                  "WHERE state1='Tamil Nadu'"),
        )

    def test_wrapped_wrong_aggregation_still_caught(self):
        self.assertIn(
            ViolationCode.AGGREGATION_MISMATCH.value,
            codes(PLAN_FILTER,
                  f"SELECT AVG(ISNULL(cy,0)) FROM {T} WHERE state1='Tamil Nadu'"),
        )

    def test_arithmetic_inside_aggregate_is_not_the_metric(self):
        """
        SUM(cy - py) is a variance, not total sales. It must not be accepted as
        SUM(cy) merely because cy appears inside.
        """

        self.assertNotEqual(
            sev(PLAN_FILTER,
                f"SELECT SUM(cy - py) FROM {T} WHERE state1='Tamil Nadu'"),
            Severity.PASS,
        )


# ===========================================================================
# GATE 5 - B. Boolean predicate safety (was a FALSE NEGATIVE)
# ===========================================================================

class TestBooleanPredicateSafety(unittest.TestCase):
    """
    A required filter only counts if the SQL guarantees it. Sitting inside an
    OR branch does not guarantee it.
    """

    def test_or_tautology_is_caught(self):
        result = verify_sql_against_plan(
            PLAN_FILTER,
            f"SELECT SUM(cy) FROM {T} WHERE state1='Tamil Nadu' OR 1=1",
        )

        self.assertNotEqual(result.severity, Severity.PASS)

    def test_or_true_is_caught(self):
        self.assertNotEqual(
            sev(PLAN_FILTER,
                f"SELECT SUM(cy) FROM {T} WHERE state1='Tamil Nadu' OR 1=1"),
            Severity.PASS,
        )

    def test_filter_only_in_or_branch_is_caught(self):
        """
        Reported as FILTER_NOT_GUARANTEED rather than MISSING_FILTER: the
        filter is written in the SQL but not enforced, which is the more
        precise and more dangerous description.
        """

        result = verify_sql_against_plan(
            PLAN_FILTER,
            f"SELECT SUM(cy) FROM {T} "
            "WHERE state1='Tamil Nadu' OR mkttype='DIRECT'",
        )

        self.assertIn(ViolationCode.FILTER_NOT_GUARANTEED.value, result.codes())
        self.assertEqual(result.severity, Severity.REPAIRABLE_FAILURE)

    def test_negated_filter_is_caught(self):
        self.assertNotEqual(
            sev(PLAN_FILTER,
                f"SELECT SUM(cy) FROM {T} WHERE NOT (state1='Tamil Nadu')"),
            Severity.PASS,
        )

    # --- the other direction: legitimate SQL must still pass ---

    def test_plain_and_still_passes(self):
        """
        Two filters the plan authorises, joined by AND. Both are guaranteed, so
        this must pass untouched. (The plan carries both filters: an extra
        filter the plan did not request is a separate rule, tested elsewhere.)
        """

        plan = SemanticPlan(
            metrics=[M()],
            filters=[
                F(),
                F("mkttype", ["DIRECT", "DISTRIBUTOR"], FilterOperator.IN),
            ],
            primary_table=T,
        )

        self.assertEqual(
            sev(plan,
                f"SELECT SUM(cy) FROM {T} "
                "WHERE state1='Tamil Nadu' AND mkttype IN ('DIRECT','DISTRIBUTOR')"),
            Severity.PASS,
        )

    def test_and_with_nested_or_still_passes(self):
        """
        The required filter is a top-level AND term. An OR elsewhere does not
        weaken it, so this must not be rejected.
        """

        plan = SemanticPlan(metrics=[M()], filters=[F()], primary_table=T)

        result = verify_sql_against_plan(
            plan,
            f"SELECT SUM(cy) FROM {T} WHERE state1='Tamil Nadu' "
            "AND (mkttype='DIRECT' OR mkttype='DISTRIBUTOR')",
        )

        self.assertNotIn(ViolationCode.MISSING_FILTER.value, result.codes())

    def test_parenthesised_and_still_passes(self):
        self.assertEqual(
            sev(PLAN_FILTER,
                f"SELECT SUM(cy) FROM {T} WHERE (state1='Tamil Nadu')"),
            Severity.PASS,
        )

    def test_in_list_filter_still_passes(self):
        plan = SemanticPlan(
            metrics=[M()],
            filters=[F(values=["Tamil Nadu", "Kerala"], op=FilterOperator.IN)],
            primary_table=T,
        )

        self.assertEqual(
            sev(plan,
                f"SELECT SUM(cy) FROM {T} "
                "WHERE state1 IN ('Tamil Nadu','Kerala')"),
            Severity.PASS,
        )


# ===========================================================================
# GATE 5 - C/D/E. HAVING, DISTINCT, unexpected row limit
# ===========================================================================

class TestHiddenRowRestrictions(unittest.TestCase):

    def test_unrequested_having_is_reported(self):
        result = verify_sql_against_plan(
            PLAN_GROUP,
            f"SELECT state1, SUM(cy) FROM {T} GROUP BY state1 "
            "HAVING SUM(cy) > 999999",
        )

        self.assertIn(ViolationCode.UNEXPECTED_HAVING.value, result.codes())

    def test_query_without_having_is_clean(self):
        self.assertNotIn(
            ViolationCode.UNEXPECTED_HAVING.value,
            codes(PLAN_GROUP,
                  f"SELECT state1, SUM(cy) FROM {T} GROUP BY state1"),
        )

    def test_unrequested_distinct_is_reported(self):
        self.assertIn(
            ViolationCode.UNEXPECTED_DISTINCT.value,
            codes(PLAN_GROUP,
                  f"SELECT DISTINCT state1, SUM(cy) FROM {T} GROUP BY state1"),
        )

    def test_query_without_distinct_is_clean(self):
        self.assertNotIn(
            ViolationCode.UNEXPECTED_DISTINCT.value,
            codes(PLAN_GROUP,
                  f"SELECT state1, SUM(cy) FROM {T} GROUP BY state1"),
        )

    def test_unexpected_top_is_caught(self):
        """
        The plan asked for a total, not a ranking. TOP 1 returns one row and
        silently answers a different question.
        """

        result = verify_sql_against_plan(
            PLAN_PLAIN, f"SELECT TOP 1 SUM(cy) FROM {T}"
        )

        self.assertIn(ViolationCode.UNEXPECTED_LIMIT.value, result.codes())
        self.assertEqual(result.severity, Severity.REPAIRABLE_FAILURE)

    def test_requested_top_is_not_flagged(self):
        self.assertNotIn(
            ViolationCode.UNEXPECTED_LIMIT.value,
            codes(PLAN_RANK,
                  f"SELECT TOP 5 state1, SUM(cy) FROM {T} "
                  "GROUP BY state1 ORDER BY SUM(cy) DESC"),
        )

    def test_no_limit_is_not_flagged(self):
        self.assertNotIn(
            ViolationCode.UNEXPECTED_LIMIT.value,
            codes(PLAN_PLAIN, f"SELECT SUM(cy) FROM {T}"),
        )


# ===========================================================================
# GATE 6 - A/D. Derived arithmetic (was a FALSE POSITIVE)
# ===========================================================================

TWO_STATES = [
    {"state1": "Tamil Nadu", "cy": Decimal("1000000")},
    {"state1": "Kerala", "cy": Decimal("750000")},
]

PLAN_G = SemanticPlan(metrics=[M()], dimensions=[D()], primary_table=T)


class TestDerivedArithmetic(unittest.TestCase):

    def test_difference_of_two_returned_values_passes(self):
        result = verify_answer_against_results(
            PLAN_G, TWO_STATES, "Kerala trails Tamil Nadu by 250000."
        )

        self.assertEqual(result.severity, Severity.PASS, result.codes())

    def test_wrong_difference_is_caught(self):
        result = verify_answer_against_results(
            PLAN_G, TWO_STATES, "Kerala trails Tamil Nadu by 300000."
        )

        self.assertIn(ViolationCode.UNSUPPORTED_NUMBER.value, result.codes())

    def test_sum_of_two_returned_values_passes(self):
        result = verify_answer_against_results(
            PLAN_G, TWO_STATES, "Together the two states reached 1750000."
        )

        self.assertEqual(result.severity, Severity.PASS, result.codes())

    def test_derivable_growth_percentage_passes(self):
        rows = [{"cy": Decimal("1200000"), "pytd": Decimal("1000000")}]

        result = verify_answer_against_results(
            SemanticPlan(metrics=[M("cy"), M("pytd")], primary_table=T),
            rows,
            "Sales of 1200000 grew 20% over 1000000.",
        )

        self.assertEqual(result.severity, Severity.PASS, result.codes())

    def test_wrong_percentage_is_still_reported(self):
        rows = [{"cy": Decimal("1200000"), "pytd": Decimal("1000000")}]

        result = verify_answer_against_results(
            SemanticPlan(metrics=[M("cy"), M("pytd")], primary_table=T),
            rows,
            "Sales of 1200000 grew 45% over 1000000.",
        )

        self.assertIn(
            ViolationCode.UNSUPPORTED_CALCULATION.value, result.codes()
        )

    def test_invented_number_still_caught_with_derivation_enabled(self):
        """
        Allowing derived values must not turn the validator into a sieve.
        9,999,999 is not reachable from these rows by any supported operation.
        """

        result = verify_answer_against_results(
            PLAN_G, TWO_STATES, "Total sales were 9999999."
        )

        self.assertIn(ViolationCode.UNSUPPORTED_NUMBER.value, result.codes())


# ===========================================================================
# GATE 6 - B. Number extraction (was a FALSE POSITIVE)
# ===========================================================================

class TestNumberExtractionInsideTokens(unittest.TestCase):
    """Digits attached to letters are labels, not figures."""

    def test_quarter_labels_are_not_figures(self):
        for text in ["Performance in Q1 was steady.",
                     "Q4 results improved.",
                     "H2 was stronger than H1."]:
            with self.subTest(text=text):
                self.assertEqual(extract_numeric_claims(text), [])

    def test_fiscal_shorthand_is_not_a_figure(self):
        self.assertEqual(extract_numeric_claims("FY25 was strong."), [])

    def test_product_codes_are_not_figures(self):
        self.assertEqual(extract_numeric_claims("Product A4 sold well."), [])

    def test_q1_answer_no_longer_false_positive(self):
        result = verify_answer_against_results(
            PLAN_G, TWO_STATES, "Overall performance in Q1 was consistent."
        )

        self.assertEqual(result.severity, Severity.PASS, result.codes())

    # --- the other direction: real numbers must still be extracted ---

    def test_real_numbers_still_extracted(self):
        cases = {
            "Sales were 2025.": "2025",
            "Sales were 1,000.": "1000",
            "Sales were 1.25M.": "1250000.00",
            "Variance was -450.75.": "-450.75",
            f"Sales were {RUPEE}1,45,23,890.50.": "14523890.50",
            "Growth was 15.5%.": "15.5",
        }

        for text, expected in cases.items():
            with self.subTest(text=text):
                claims = extract_numeric_claims(text)

                self.assertEqual(len(claims), 1, f"{text} -> {claims}")
                self.assertEqual(str(claims[0].value), expected)

    def test_invented_number_still_caught(self):
        result = verify_answer_against_results(
            PLAN_G, TWO_STATES, "Sales in Q1 were 8888888."
        )

        self.assertIn(ViolationCode.UNSUPPORTED_NUMBER.value, result.codes())


# ===========================================================================
# GATE 6 - C. Entity detection (was a FALSE POSITIVE)
# ===========================================================================

PARTY_ROWS = [{"cardname": "ABC Traders", "cy": Decimal("400000")}]


class TestEntityDetection(unittest.TestCase):

    def test_entity_inside_a_longer_value_is_not_flagged(self):
        result = verify_answer_against_results(
            PLAN_G, PARTY_ROWS, "ABC Traders contributed 400000."
        )

        self.assertNotIn(
            ViolationCode.ENTITY_NOT_IN_RESULTS.value, result.codes()
        )

    def test_partial_token_of_a_known_value_is_not_flagged(self):
        result = verify_answer_against_results(
            PLAN_G, PARTY_ROWS, "ABC contributed 400000."
        )

        self.assertNotIn(
            ViolationCode.ENTITY_NOT_IN_RESULTS.value, result.codes()
        )

    def test_genuinely_absent_entity_is_still_warned(self):
        result = verify_answer_against_results(
            PLAN_G, PARTY_ROWS, "XYZ ENTERPRISES contributed 400000."
        )

        self.assertIn(ViolationCode.ENTITY_NOT_IN_RESULTS.value, result.codes())
        self.assertEqual(result.severity, Severity.WARNING)


# ===========================================================================
# Determinism
# ===========================================================================

class TestDeterminismOfFixes(unittest.TestCase):

    def test_sql_guard_repeats_identically(self):
        sql = f"SELECT SUM(ISNULL(cy,0)) FROM {T} WHERE state1='Tamil Nadu' OR 1=1"

        first = verify_sql_against_plan(PLAN_FILTER, sql)

        for _ in range(25):
            again = verify_sql_against_plan(PLAN_FILTER, sql)

            self.assertEqual(again.codes(), first.codes())
            self.assertEqual(again.severity, first.severity)

    def test_grounding_repeats_identically(self):
        answer = "Kerala trails Tamil Nadu by 250000 in Q1."

        first = verify_answer_against_results(PLAN_G, TWO_STATES, answer)

        for _ in range(25):
            again = verify_answer_against_results(PLAN_G, TWO_STATES, answer)

            self.assertEqual(again.codes(), first.codes())
            self.assertEqual(again.severity, first.severity)


if __name__ == "__main__":
    unittest.main(verbosity=2)
