"""
Gate 6 Step 33 - tests for answer grounding.

Deterministic throughout: no model, no database, no network. Regeneration is an
injected callable, so the retry path is exercised without an LLM.

Every rule is tested in both directions - a wrong answer is caught, and a
legitimate answer written differently is accepted. The second half matters as
much as the first: a validator that rejects correct answers gets switched off.
"""

import os
import sys
import unittest
from decimal import Decimal

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.guard.grounding import (
    MODE_ENFORCE,
    MODE_OFF,
    MODE_SHADOW,
    build_supported_values,
    format_grounding_feedback,
    get_grounding_mode,
    ground_answer,
    verify_answer_against_results,
)
from ai.guard.models import Severity, ViolationCode
from ai.guard.numbers import extract_numeric_claims, extract_years, parse_number

from semantic.models.semantic_plan import (
    FilterOperator,
    RankDirection,
    RankMeasure,
    SemanticFilter,
    SemanticIntent,
    SemanticMetric,
    SemanticPlan,
    SemanticRanking,
)

RUPEE = "₹"

SALES = "QB_MDJMD_SALES_5YRS_SUMMARY"


def sum_plan(column="TotalSales", aggregation="SUM"):
    return SemanticPlan(
        intent=SemanticIntent.AGGREGATE,
        metrics=[
            SemanticMetric(
                metric_name="cy",
                business_name="Sales",
                table_name=SALES,
                column_name=column,
                aggregation_type=aggregation,
            )
        ],
        primary_table=SALES,
    )


ONE_MILLION = [{"TotalSales": Decimal("1000000")}]


class Spy:
    def __init__(self, result=None):
        self.calls = []
        self.result = result

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result

    @property
    def count(self):
        return len(self.calls)


# ---------------------------------------------------------------------------
# PASS cases - legitimate answers must be accepted
# ---------------------------------------------------------------------------

class TestAcceptsCorrectAnswers(unittest.TestCase):

    def setUp(self):
        self.plan = sum_plan()

    def _assert_ok(self, answer, rows=None):
        result = verify_answer_against_results(
            self.plan, rows if rows is not None else ONE_MILLION, answer
        )

        self.assertEqual(
            result.severity, Severity.PASS, f"{answer!r} -> {result.codes()}"
        )

    def test_exact_value(self):
        self._assert_ok("Total sales were 1000000.")

    def test_western_grouping(self):
        self._assert_ok("Total sales were 1,000,000.")

    def test_indian_currency_formatting(self):
        """The model is shown Indian grouping, so it echoes it back."""

        self._assert_ok(f"Total sales were {RUPEE}10,00,000.")

    def test_scaled_millions(self):
        self._assert_ok("Total sales were 1M.")
        self._assert_ok("Total sales were 1.0M.")
        self._assert_ok("Total sales were 1 million.")

    def test_indian_scale_words(self):
        self._assert_ok("Total sales were 10 lakh.")

    def test_crore(self):
        self._assert_ok(
            "Total sales were 1 crore.",
            rows=[{"TotalSales": Decimal("10000000")}],
        )

    def test_zero(self):
        self._assert_ok("Total sales were 0.", rows=[{"TotalSales": 0}])

    def test_negative(self):
        self._assert_ok(
            "The variance was -450.75.",
            rows=[{"TotalSales": Decimal("-450.75")}],
        )

    def test_decimals(self):
        self._assert_ok(
            "Total sales were 1234.56.",
            rows=[{"TotalSales": Decimal("1234.56")}],
        )

    def test_percentage_present_in_results(self):
        self._assert_ok(
            "Margin was 15.5%.",
            rows=[{"TotalSales": Decimal("1000000"), "Margin": Decimal("15.5")}],
        )

    def test_correct_row_count(self):
        rows = [{"State1": f"S{i}", "TotalSales": Decimal(i)} for i in range(25)]

        self._assert_ok("There were 25 records returned.", rows=rows)

    def test_answer_with_no_numbers(self):
        self._assert_ok("Sales performed strongly across the region.")

    def test_null_values_do_not_fail(self):
        self._assert_ok(
            "Total sales were 1,000,000.",
            rows=[{"TotalSales": Decimal("1000000"), "Target": None}],
        )

    def test_duplicate_values_across_rows(self):
        self._assert_ok(
            "Two states each recorded 500.",
            rows=[{"S": "A", "TotalSales": 500}, {"S": "B", "TotalSales": 500}],
        )

    def test_multiple_metrics(self):
        self._assert_ok(
            "Sales were 1,000,000 and quantity was 250.",
            rows=[{"TotalSales": Decimal("1000000"), "Qty": 250}],
        )

    def test_value_beyond_serializer_row_limit_is_supported(self):
        """
        The serializer shows the model only 20 rows, but every returned row is
        legitimate ground truth. A figure from row 30 must not be rejected.
        """

        rows = [{"TotalSales": Decimal(i)} for i in range(1, 41)]

        self._assert_ok("One region recorded 37.", rows=rows)

    def test_non_currency_column_raw_value(self):
        self._assert_ok(
            "The count was 1000000.",
            rows=[{"RandomCount": Decimal("1000000")}],
        )

    def test_years_are_not_treated_as_figures(self):
        """A year names a period. It must not be read as an unsupported figure."""

        self._assert_ok("In 2024 total sales were 1,000,000.")

    def test_fiscal_span_is_not_treated_as_figures(self):
        self._assert_ok("In FY 2024-25 total sales were 1,000,000.")

    def test_correct_aggregation_wording(self):
        self._assert_ok("The total sales figure was 1,000,000.")

    def test_average_wording_allowed_when_plan_says_avg(self):
        plan = sum_plan(aggregation="AVG")

        result = verify_answer_against_results(
            plan, ONE_MILLION, "The average was 1,000,000."
        )

        self.assertEqual(result.severity, Severity.PASS)

    def test_rounded_formatted_value_is_supported(self):
        """
        format_indian_currency rounds to two decimals, so the model sees .57
        where the row holds .567. Quoting what it was shown must pass.
        """

        result = verify_answer_against_results(
            sum_plan(),
            [{"TotalSales": Decimal("1234.567")}],
            f"Sales were {RUPEE}1,234.57.",
        )

        self.assertEqual(result.severity, Severity.PASS, result.codes())

    def test_requested_top_n_is_supported(self):
        plan = SemanticPlan(
            metrics=[
                SemanticMetric(
                    metric_name="cy",
                    business_name="Sales",
                    table_name=SALES,
                    column_name="TotalSales",
                    aggregation_type="SUM",
                )
            ],
            ranking=SemanticRanking(
                top_n=5,
                direction=RankDirection.DESC,
                measure=RankMeasure.ABSOLUTE,
            ),
        )

        result = verify_answer_against_results(
            plan, ONE_MILLION, "The top 5 states totalled 1,000,000."
        )

        self.assertEqual(result.severity, Severity.PASS, result.codes())


# ---------------------------------------------------------------------------
# FAIL cases
# ---------------------------------------------------------------------------

class TestCatchesUngroundedAnswers(unittest.TestCase):

    def setUp(self):
        self.plan = sum_plan()

    def _codes(self, answer, rows=None):
        result = verify_answer_against_results(
            self.plan, rows if rows is not None else ONE_MILLION, answer
        )
        return result.codes()

    def test_invented_number(self):
        self.assertIn(
            ViolationCode.UNSUPPORTED_NUMBER.value,
            self._codes("Total sales were 2,500,000."),
        )

    def test_digit_altered_number(self):
        self.assertIn(
            ViolationCode.UNSUPPORTED_NUMBER.value,
            self._codes("Total sales were 1,000,001."),
        )

    def test_scaled_value_that_does_not_match(self):
        """1.2M is the dangerous case - plausible, close, and wrong."""

        self.assertIn(
            ViolationCode.UNSUPPORTED_NUMBER.value,
            self._codes("Total sales were 1.2M."),
        )

    def test_wrong_lakh_value(self):
        self.assertIn(
            ViolationCode.UNSUPPORTED_NUMBER.value,
            self._codes("Total sales were 11 lakh."),
        )

    def test_wrong_row_count(self):
        rows = [{"TotalSales": Decimal(i)} for i in range(25)]

        self.assertIn(
            ViolationCode.ROW_COUNT_MISMATCH.value,
            self._codes("There were 30 records returned.", rows=rows),
        )

    def test_numbers_when_no_rows_returned(self):
        codes = self._codes("Total sales were 1,000,000.", rows=[])

        self.assertIn(ViolationCode.NUMBERS_WITHOUT_RESULTS.value, codes)

    def test_contradictory_aggregation_wording(self):
        self.assertIn(
            ViolationCode.AGGREGATION_WORDING_CONTRADICTION.value,
            self._codes("The average sales were 1,000,000."),
        )

    def test_severity_is_repairable_not_hard(self):
        result = verify_answer_against_results(
            self.plan, ONE_MILLION, "Total sales were 2,500,000."
        )

        self.assertEqual(result.severity, Severity.REPAIRABLE_FAILURE)
        self.assertFalse(result.passed)


class TestPeriodGrounding(unittest.TestCase):

    def _plan_with_period(self):
        import datetime

        from semantic.temporal.enums import TimeStrategyType
        from semantic.temporal.models import TimeContext

        class _Intent:
            pass

        context = TimeContext(
            intent=_Intent(),
            strategy=TimeStrategyType.DATE_RANGE
            if hasattr(TimeStrategyType, "DATE_RANGE")
            else list(TimeStrategyType)[0],
            start_date=datetime.date(2024, 4, 1),
            end_date=datetime.date(2025, 3, 31),
        )

        plan = sum_plan()

        return plan.model_copy(update={"temporal": context})

    def test_correct_year_passes(self):
        result = verify_answer_against_results(
            self._plan_with_period(),
            ONE_MILLION,
            "In FY 2024-25 sales were 1,000,000.",
        )

        self.assertNotIn(
            ViolationCode.PERIOD_CONTRADICTION.value, result.codes()
        )

    def test_wrong_year_is_caught(self):
        result = verify_answer_against_results(
            self._plan_with_period(),
            ONE_MILLION,
            "In FY 2019-20 sales were 1,000,000.",
        )

        self.assertIn(ViolationCode.PERIOD_CONTRADICTION.value, result.codes())

    def test_no_temporal_context_disables_the_check(self):
        result = verify_answer_against_results(
            sum_plan(), ONE_MILLION, "In 1999 sales were 1,000,000."
        )

        self.assertNotIn(
            ViolationCode.PERIOD_CONTRADICTION.value, result.codes()
        )


class TestWarningOnlyRules(unittest.TestCase):
    """These record. They must never block."""

    def test_derived_percentage_is_a_warning(self):
        result = verify_answer_against_results(
            sum_plan(), ONE_MILLION, "Sales of 1,000,000 grew by 14.5%."
        )

        self.assertIn(
            ViolationCode.UNSUPPORTED_CALCULATION.value, result.codes()
        )
        self.assertEqual(result.severity, Severity.WARNING)
        self.assertTrue(result.passed)

    def test_unknown_entity_is_a_warning(self):
        result = verify_answer_against_results(
            sum_plan(),
            [{"State1": "TN", "TotalSales": Decimal("1000000")}],
            "KARNATAKA recorded 1,000,000.",
        )

        self.assertIn(ViolationCode.ENTITY_NOT_IN_RESULTS.value, result.codes())
        self.assertEqual(result.severity, Severity.WARNING)
        self.assertTrue(result.passed)

    def test_known_entity_is_not_flagged(self):
        result = verify_answer_against_results(
            sum_plan(),
            [{"State1": "TN", "TotalSales": Decimal("1000000")}],
            "TN recorded 1,000,000.",
        )

        self.assertNotIn(
            ViolationCode.ENTITY_NOT_IN_RESULTS.value, result.codes()
        )

    def test_common_abbreviations_are_not_flagged(self):
        result = verify_answer_against_results(
            sum_plan(),
            [{"State1": "TN", "TotalSales": Decimal("1000000")}],
            "CY sales and YTD totals reached 1,000,000.",
        )

        self.assertNotIn(
            ViolationCode.ENTITY_NOT_IN_RESULTS.value, result.codes()
        )


# ---------------------------------------------------------------------------
# Numeric engine edge cases
# ---------------------------------------------------------------------------

class TestNumericExtraction(unittest.TestCase):

    def test_dates_are_not_figures(self):
        claims = extract_numeric_claims("On 2025-04-01 the value was 500.")

        self.assertEqual([str(c.value) for c in claims], ["500"])

    def test_negative_sign_is_kept(self):
        claims = extract_numeric_claims("Variance was -450.75 overall.")

        self.assertEqual(str(claims[0].value), "-450.75")

    def test_range_hyphen_is_not_a_minus(self):
        claims = extract_numeric_claims("Range 10-20 units.")

        self.assertEqual([str(c.value) for c in claims], ["10", "20"])

    def test_sentence_ending_full_stop(self):
        claims = extract_numeric_claims("Sales were 1,000,000.")

        self.assertEqual(str(claims[0].value), "1000000")

    def test_scale_letter_not_taken_from_a_word(self):
        claims = extract_numeric_claims("We used 1 method here.")

        self.assertEqual(str(claims[0].value), "1")

    def test_bare_year_flagged(self):
        claims = extract_numeric_claims("In 2024 sales rose.")

        self.assertTrue(claims[0].is_bare_year)

    def test_currency_amount_is_not_a_year(self):
        claims = extract_numeric_claims(f"Sales were {RUPEE}2024.")

        self.assertFalse(claims[0].is_bare_year)

    def test_fiscal_years_expand(self):
        self.assertEqual(extract_years("FY 2024-25"), {2024, 2025})

    def test_parse_formatted_currency(self):
        self.assertEqual(parse_number(f"{RUPEE}10,00,000"), Decimal("1000000"))


class TestSupportedValues(unittest.TestCase):

    def test_includes_raw_and_formatted(self):
        supported = build_supported_values(
            sum_plan(), [{"TotalSales": Decimal("1234.567")}]
        )

        self.assertIn(Decimal("1234.567"), supported)
        self.assertIn(Decimal("1234.57"), supported)

    def test_includes_row_count(self):
        supported = build_supported_values(
            sum_plan(), [{"A": 1}, {"A": 2}, {"A": 3}]
        )

        self.assertIn(Decimal(3), supported)

    def test_booleans_are_not_numbers(self):
        """
        True must not become 1. Two rows are used so that the legitimate row
        count (2) cannot be mistaken for the boolean having been counted.
        """

        supported = build_supported_values(
            sum_plan(), [{"Flag": True}, {"Flag": True}]
        )

        self.assertNotIn(Decimal(1), supported)
        self.assertIn(Decimal(2), supported)


# ---------------------------------------------------------------------------
# Modes, retry and orchestration
# ---------------------------------------------------------------------------

class TestShadowMode(unittest.TestCase):

    def test_violation_does_not_block(self):
        decision = ground_answer(
            plan=sum_plan(),
            rows=ONE_MILLION,
            answer="Sales were 9,999,999.",
            mode=MODE_SHADOW,
        )

        self.assertFalse(decision.blocked)
        self.assertTrue(decision.shadow_violation)

    def test_answer_is_unchanged(self):
        answer = "Sales were 9,999,999."

        decision = ground_answer(
            plan=sum_plan(), rows=ONE_MILLION, answer=answer, mode=MODE_SHADOW
        )

        self.assertEqual(decision.answer, answer)

    def test_no_regeneration_in_shadow(self):
        regenerate = Spy(result="Sales were 1,000,000.")

        ground_answer(
            plan=sum_plan(),
            rows=ONE_MILLION,
            answer="Sales were 9,999,999.",
            regenerate=regenerate,
            mode=MODE_SHADOW,
        )

        self.assertEqual(regenerate.count, 0)

    def test_violation_is_logged(self):
        with self.assertLogs("ai.guard.grounding", level="WARNING") as captured:
            ground_answer(
                plan=sum_plan(),
                rows=ONE_MILLION,
                answer="Sales were 9,999,999.",
                mode=MODE_SHADOW,
            )

        self.assertTrue(
            any("Answer grounding violation" in line for line in captured.output)
        )


class TestOffMode(unittest.TestCase):

    def test_validator_does_not_run(self):
        decision = ground_answer(
            plan=sum_plan(),
            rows=ONE_MILLION,
            answer="Sales were 9,999,999.",
            mode=MODE_OFF,
        )

        self.assertFalse(decision.blocked)
        self.assertIsNone(decision.first_result)


class TestModeConfiguration(unittest.TestCase):

    def test_default_is_shadow(self):
        previous = os.environ.pop("ANSWER_GUARD_MODE", None)

        try:
            self.assertEqual(get_grounding_mode(), MODE_SHADOW)
        finally:
            if previous is not None:
                os.environ["ANSWER_GUARD_MODE"] = previous

    def test_invalid_mode_falls_back_to_shadow(self):
        previous = os.environ.get("ANSWER_GUARD_MODE")
        os.environ["ANSWER_GUARD_MODE"] = "banana"

        try:
            self.assertEqual(get_grounding_mode(), MODE_SHADOW)
        finally:
            if previous is None:
                os.environ.pop("ANSWER_GUARD_MODE", None)
            else:
                os.environ["ANSWER_GUARD_MODE"] = previous


class TestEnforcementRetry(unittest.TestCase):

    def setUp(self):
        self.plan = sum_plan()

    def test_grounded_answer_never_regenerates(self):
        regenerate = Spy(result="x")

        decision = ground_answer(
            plan=self.plan,
            rows=ONE_MILLION,
            answer="Sales were 1,000,000.",
            regenerate=regenerate,
            mode=MODE_ENFORCE,
        )

        self.assertFalse(decision.blocked)
        self.assertEqual(regenerate.count, 0)

    def test_retry_happens_exactly_once(self):
        regenerate = Spy(result="Sales were 1,000,000.")

        decision = ground_answer(
            plan=self.plan,
            rows=ONE_MILLION,
            answer="Sales were 9,999,999.",
            regenerate=regenerate,
            mode=MODE_ENFORCE,
        )

        self.assertEqual(regenerate.count, 1)
        self.assertTrue(decision.retried)
        self.assertEqual(decision.attempts, 2)

    def test_successful_retry_returns_corrected_answer(self):
        decision = ground_answer(
            plan=self.plan,
            rows=ONE_MILLION,
            answer="Sales were 9,999,999.",
            regenerate=lambda f: "Sales were 1,000,000.",
            mode=MODE_ENFORCE,
        )

        self.assertFalse(decision.blocked)
        self.assertEqual(decision.answer, "Sales were 1,000,000.")

    def test_still_ungrounded_after_retry_is_blocked(self):
        regenerate = Spy(result="Sales were 8,888,888.")

        decision = ground_answer(
            plan=self.plan,
            rows=ONE_MILLION,
            answer="Sales were 9,999,999.",
            regenerate=regenerate,
            mode=MODE_ENFORCE,
        )

        self.assertTrue(decision.blocked)
        self.assertEqual(regenerate.count, 1, "must not retry twice")

    def test_blocked_answer_is_not_returned_as_valid(self):
        decision = ground_answer(
            plan=self.plan,
            rows=ONE_MILLION,
            answer="Sales were 9,999,999.",
            regenerate=lambda f: "Sales were 8,888,888.",
            mode=MODE_ENFORCE,
        )

        self.assertTrue(decision.blocked)
        self.assertIsNotNone(decision.message)

    def test_original_rows_and_plan_used_for_recheck(self):
        """
        The rewrite is judged against the same plan and the same rows. Here the
        rewrite quotes a figure valid only under different data, so it must
        still be rejected.
        """

        decision = ground_answer(
            plan=self.plan,
            rows=ONE_MILLION,
            answer="Sales were 9,999,999.",
            regenerate=lambda f: "Sales were 7,777,777.",
            mode=MODE_ENFORCE,
        )

        self.assertTrue(decision.blocked)
        self.assertIn(
            ViolationCode.UNSUPPORTED_NUMBER.value,
            decision.final_result.codes(),
        )

    def test_empty_rewrite_is_blocked(self):
        for empty in [None, "", "   "]:
            with self.subTest(value=repr(empty)):
                decision = ground_answer(
                    plan=self.plan,
                    rows=ONE_MILLION,
                    answer="Sales were 9,999,999.",
                    regenerate=lambda f: empty,
                    mode=MODE_ENFORCE,
                )

                self.assertTrue(decision.blocked)

    def test_regeneration_raising_is_blocked(self):
        def explode(feedback):
            raise RuntimeError("provider unavailable")

        decision = ground_answer(
            plan=self.plan,
            rows=ONE_MILLION,
            answer="Sales were 9,999,999.",
            regenerate=explode,
            mode=MODE_ENFORCE,
        )

        self.assertTrue(decision.blocked)

    def test_missing_regenerate_callable_blocks(self):
        decision = ground_answer(
            plan=self.plan,
            rows=ONE_MILLION,
            answer="Sales were 9,999,999.",
            mode=MODE_ENFORCE,
        )

        self.assertTrue(decision.blocked)

    def test_warning_only_answer_is_not_regenerated(self):
        regenerate = Spy(result="x")

        decision = ground_answer(
            plan=self.plan,
            rows=ONE_MILLION,
            answer="Sales of 1,000,000 grew by 14.5%.",
            regenerate=regenerate,
            mode=MODE_ENFORCE,
        )

        self.assertFalse(decision.blocked)
        self.assertEqual(regenerate.count, 0)


class TestFeedback(unittest.TestCase):

    def test_feedback_names_the_problem(self):
        result = verify_answer_against_results(
            sum_plan(), ONE_MILLION, "Sales were 2,500,000."
        )

        feedback = format_grounding_feedback(result)

        self.assertIn("ANSWER GROUNDING FAILURE", feedback)
        self.assertIn("UNSUPPORTED_NUMBER", feedback)
        self.assertIn("2,500,000", feedback)

    def test_feedback_excludes_warnings(self):
        result = verify_answer_against_results(
            sum_plan(), ONE_MILLION, "Sales were 2,500,000 and grew 14.5%."
        )

        feedback = format_grounding_feedback(result)

        self.assertIn(ViolationCode.UNSUPPORTED_NUMBER.value, feedback)
        self.assertNotIn(ViolationCode.UNSUPPORTED_CALCULATION.value, feedback)


class TestDeterminism(unittest.TestCase):

    def test_identical_every_time(self):
        plan = sum_plan()
        answer = "Sales were 2,500,000 and grew 14.5%."

        first = verify_answer_against_results(plan, ONE_MILLION, answer)

        for _ in range(30):
            again = verify_answer_against_results(plan, ONE_MILLION, answer)

            self.assertEqual(again.codes(), first.codes())
            self.assertEqual(again.severity, first.severity)
            self.assertEqual(again.passed, first.passed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
