"""
Gate 5 Step 32 - integration tests for guard wiring, shadow mode and retry.

No model is called and no database is touched. Regeneration and revalidation
are injected callables, so every path - including the ones that must never
reach the database - is exercised deterministically.

The database-safety tests mirror the sequence app.py performs: validate, guard,
and only then execute. They use a spy in place of the database and assert it
was never invoked. They exercise that ordering rather than running FastAPI,
which would require the full auth, session and connection stack.
"""

import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.guard.enforcement import (
    MODE_ENFORCE,
    MODE_OFF,
    MODE_SHADOW,
    GuardDecision,
    format_guard_feedback,
    get_guard_mode,
    guard_sql,
)
from ai.guard.models import Severity, ViolationCode
from ai.guard.plan_conformance import verify_sql_against_plan

from semantic.models.semantic_plan import (
    FilterOperator,
    RankDirection,
    SemanticDimension,
    SemanticFilter,
    SemanticIntent,
    SemanticJoin,
    SemanticMetric,
    SemanticPlan,
    SemanticQueryShape,
    SemanticRanking,
    SemanticTable,
)


SALES = "QB_MDJMD_SALES_5YRS_SUMMARY"
STATE = "DimState"


def plan_sum_cy_tamil_nadu() -> SemanticPlan:
    """SUM(CY) WHERE State1 = 'Tamil Nadu'."""

    return SemanticPlan(
        intent=SemanticIntent.AGGREGATE,
        metrics=[
            SemanticMetric(
                metric_name="cy",
                business_name="Sales",
                table_name=SALES,
                column_name="CY",
                aggregation_type="SUM",
            )
        ],
        filters=[
            SemanticFilter(
                dimension_name="state",
                table_name=SALES,
                column_name="State1",
                operator=FilterOperator.EQUAL,
                values=["Tamil Nadu"],
            )
        ],
        primary_table=SALES,
        query_shape=SemanticQueryShape.SINGLE_VALUE,
    )


CORRECT_SQL = f"SELECT SUM(CY) FROM {SALES} WHERE State1 = 'Tamil Nadu'"
WRONG_METRIC = f"SELECT SUM(PY) FROM {SALES} WHERE State1 = 'Tamil Nadu'"
WRONG_AGG = f"SELECT AVG(CY) FROM {SALES} WHERE State1 = 'Tamil Nadu'"
WRONG_VALUE = f"SELECT SUM(CY) FROM {SALES} WHERE State1 = 'Karnataka'"
NO_FILTER = f"SELECT SUM(CY) FROM {SALES}"
MALFORMED = "SELECT FROM WHERE"


class Spy:
    """Records calls so a test can assert something never happened."""

    def __init__(self, result=None):
        self.calls = []
        self.result = result

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result

    @property
    def count(self):
        return len(self.calls)


def accept_all(sql):
    """Stand-in for validate_sql_query when the replacement is valid."""

    return True, sql


def reject_all(sql):
    return False, "Column 'Ghost' does not exist."


# ---------------------------------------------------------------------------
# Guard detection through the integration entry point
# ---------------------------------------------------------------------------

class TestGuardDetection(unittest.TestCase):
    """The Step 31 rules still fire when reached via guard_sql."""

    def setUp(self):
        self.plan = plan_sum_cy_tamil_nadu()

    def _codes(self, sql):
        decision = guard_sql(plan=self.plan, sql=sql, mode=MODE_SHADOW)
        return decision.codes()

    def test_correct_sql_passes(self):
        decision = guard_sql(plan=self.plan, sql=CORRECT_SQL, mode=MODE_SHADOW)

        self.assertFalse(decision.blocked)
        self.assertFalse(decision.shadow_violation)
        self.assertEqual(decision.codes(), [])

    def test_wrong_metric_detected(self):
        self.assertIn(ViolationCode.METRIC_MISMATCH.value, self._codes(WRONG_METRIC))

    def test_wrong_aggregation_detected(self):
        self.assertIn(
            ViolationCode.AGGREGATION_MISMATCH.value, self._codes(WRONG_AGG)
        )

    def test_wrong_filter_value_detected(self):
        self.assertIn(
            ViolationCode.FILTER_VALUE_MISMATCH.value, self._codes(WRONG_VALUE)
        )

    def test_missing_filter_detected(self):
        self.assertIn(ViolationCode.MISSING_FILTER.value, self._codes(NO_FILTER))

    def test_malformed_sql_detected_as_hard_failure(self):
        decision = guard_sql(plan=self.plan, sql=MALFORMED, mode=MODE_SHADOW)

        self.assertIn(ViolationCode.SQL_PARSE_FAILURE.value, decision.codes())
        self.assertEqual(decision.first_result.severity, Severity.HARD_FAILURE)

    def test_wrong_join_detected(self):
        plan = SemanticPlan(
            metrics=[
                SemanticMetric(
                    metric_name="cy",
                    business_name="Sales",
                    table_name=SALES,
                    column_name="CY",
                    aggregation_type="SUM",
                )
            ],
            joins=[
                SemanticJoin(
                    source_table=SALES,
                    source_key="StateKey",
                    target_table=STATE,
                    target_key="StateKey",
                )
            ],
            primary_table=SALES,
            relevant_tables=[
                SemanticTable(table_name=SALES),
                SemanticTable(table_name=STATE),
            ],
        )

        decision = guard_sql(
            plan=plan,
            sql=f"SELECT SUM(s.CY) FROM {SALES} s "
                f"JOIN {STATE} d ON s.RegionKey = d.RegionKey",
            mode=MODE_SHADOW,
        )

        self.assertIn(ViolationCode.JOIN_KEY_MISMATCH.value, decision.codes())

    def test_grouping_warning_does_not_block_even_in_enforce(self):
        plan = SemanticPlan(
            metrics=[
                SemanticMetric(
                    metric_name="cy",
                    business_name="Sales",
                    table_name=SALES,
                    column_name="CY",
                    aggregation_type="SUM",
                )
            ],
            dimensions=[
                SemanticDimension(
                    dimension_name="state",
                    business_name="State",
                    table_name=SALES,
                    column_name="State1",
                )
            ],
            primary_table=SALES,
        )

        regenerate = Spy()

        decision = guard_sql(
            plan=plan,
            sql=f"SELECT MktType, SUM(CY) FROM {SALES} GROUP BY MktType",
            regenerate=regenerate,
            revalidate=accept_all,
            mode=MODE_ENFORCE,
        )

        self.assertFalse(decision.blocked)
        self.assertEqual(
            regenerate.count, 0, "a WARNING must not trigger regeneration"
        )


# ---------------------------------------------------------------------------
# Shadow mode
# ---------------------------------------------------------------------------

class TestShadowMode(unittest.TestCase):
    """Shadow mode measures. It must never change an outcome."""

    def setUp(self):
        self.plan = plan_sum_cy_tamil_nadu()

    def test_violation_does_not_block(self):
        decision = guard_sql(plan=self.plan, sql=WRONG_VALUE, mode=MODE_SHADOW)

        self.assertFalse(decision.blocked)
        self.assertTrue(decision.shadow_violation)

    def test_hard_failure_does_not_block_in_shadow(self):
        decision = guard_sql(plan=self.plan, sql=MALFORMED, mode=MODE_SHADOW)

        self.assertFalse(decision.blocked)

    def test_missing_plan_does_not_block_in_shadow(self):
        decision = guard_sql(plan=None, sql=CORRECT_SQL, mode=MODE_SHADOW)

        self.assertFalse(decision.blocked)

    def test_sql_is_never_altered_in_shadow(self):
        for sql in [CORRECT_SQL, WRONG_METRIC, WRONG_VALUE, NO_FILTER]:
            with self.subTest(sql=sql):
                decision = guard_sql(plan=self.plan, sql=sql, mode=MODE_SHADOW)

                self.assertEqual(decision.sql, sql)

    def test_no_regeneration_in_shadow(self):
        regenerate = Spy(result=CORRECT_SQL)

        decision = guard_sql(
            plan=self.plan,
            sql=WRONG_VALUE,
            regenerate=regenerate,
            revalidate=accept_all,
            mode=MODE_SHADOW,
        )

        self.assertEqual(regenerate.count, 0)
        self.assertFalse(decision.retried)

    def test_violation_is_logged(self):
        with self.assertLogs("ai.guard.enforcement", level="WARNING") as captured:
            guard_sql(plan=self.plan, sql=WRONG_VALUE, mode=MODE_SHADOW)

        self.assertTrue(
            any("Plan conformance violation" in line for line in captured.output)
        )

    def test_conforming_sql_logs_nothing(self):
        logger_name = "ai.guard.enforcement"

        with self.assertLogs(logger_name, level="WARNING") as captured:
            guard_sql(plan=self.plan, sql=CORRECT_SQL, mode=MODE_SHADOW)
            # assertLogs fails when nothing is logged, so emit a marker.
            import logging

            logging.getLogger(logger_name).warning("marker")

        self.assertEqual(len(captured.output), 1)


class TestOffMode(unittest.TestCase):

    def test_guard_does_not_run(self):
        decision = guard_sql(plan=None, sql=WRONG_VALUE, mode=MODE_OFF)

        self.assertFalse(decision.blocked)
        self.assertIsNone(decision.first_result)


class TestModeConfiguration(unittest.TestCase):

    def test_default_is_shadow(self):
        previous = os.environ.pop("SQL_GUARD_MODE", None)

        try:
            self.assertEqual(get_guard_mode(), MODE_SHADOW)
        finally:
            if previous is not None:
                os.environ["SQL_GUARD_MODE"] = previous

    def test_invalid_mode_falls_back_to_shadow(self):
        previous = os.environ.get("SQL_GUARD_MODE")
        os.environ["SQL_GUARD_MODE"] = "banana"

        try:
            self.assertEqual(get_guard_mode(), MODE_SHADOW)
        finally:
            if previous is None:
                os.environ.pop("SQL_GUARD_MODE", None)
            else:
                os.environ["SQL_GUARD_MODE"] = previous


# ---------------------------------------------------------------------------
# Enforcement and retry
# ---------------------------------------------------------------------------

class TestEnforcementRetry(unittest.TestCase):

    def setUp(self):
        self.plan = plan_sum_cy_tamil_nadu()

    def test_conforming_sql_never_regenerates(self):
        regenerate = Spy(result=CORRECT_SQL)

        decision = guard_sql(
            plan=self.plan,
            sql=CORRECT_SQL,
            regenerate=regenerate,
            revalidate=accept_all,
            mode=MODE_ENFORCE,
        )

        self.assertFalse(decision.blocked)
        self.assertEqual(regenerate.count, 0)
        self.assertEqual(decision.attempts, 1)

    def test_retry_happens_exactly_once(self):
        regenerate = Spy(result=CORRECT_SQL)

        decision = guard_sql(
            plan=self.plan,
            sql=WRONG_AGG,
            regenerate=regenerate,
            revalidate=accept_all,
            mode=MODE_ENFORCE,
        )

        self.assertEqual(regenerate.count, 1, "exactly one regeneration")
        self.assertTrue(decision.retried)
        self.assertEqual(decision.attempts, 2)

    def test_retry_success_returns_regenerated_sql(self):
        decision = guard_sql(
            plan=self.plan,
            sql=WRONG_AGG,
            regenerate=lambda feedback: CORRECT_SQL,
            revalidate=accept_all,
            mode=MODE_ENFORCE,
        )

        self.assertFalse(decision.blocked)
        self.assertEqual(decision.sql, CORRECT_SQL)

    def test_still_violating_after_retry_is_blocked(self):
        regenerate = Spy(result=WRONG_VALUE)

        decision = guard_sql(
            plan=self.plan,
            sql=WRONG_AGG,
            regenerate=regenerate,
            revalidate=accept_all,
            mode=MODE_ENFORCE,
        )

        self.assertTrue(decision.blocked)
        self.assertEqual(regenerate.count, 1, "must not retry a second time")
        self.assertIn("not executed", decision.message)

    def test_regenerated_sql_is_revalidated(self):
        revalidate = Spy(result=(True, CORRECT_SQL))

        guard_sql(
            plan=self.plan,
            sql=WRONG_AGG,
            regenerate=lambda feedback: CORRECT_SQL,
            revalidate=revalidate,
            mode=MODE_ENFORCE,
        )

        self.assertEqual(
            revalidate.count, 1, "regenerated SQL must be revalidated"
        )
        self.assertEqual(revalidate.calls[0][0][0], CORRECT_SQL)

    def test_regenerated_sql_failing_validation_is_blocked(self):
        decision = guard_sql(
            plan=self.plan,
            sql=WRONG_AGG,
            regenerate=lambda feedback: "SELECT SUM(CY) FROM Ghost",
            revalidate=reject_all,
            mode=MODE_ENFORCE,
        )

        self.assertTrue(decision.blocked)
        self.assertIn("failed validation", decision.message)

    def test_malformed_regenerated_sql_is_blocked(self):
        decision = guard_sql(
            plan=self.plan,
            sql=WRONG_AGG,
            regenerate=lambda feedback: MALFORMED,
            revalidate=accept_all,
            mode=MODE_ENFORCE,
        )

        self.assertTrue(decision.blocked)

    def test_hard_failure_blocks_without_retry(self):
        regenerate = Spy(result=CORRECT_SQL)

        decision = guard_sql(
            plan=self.plan,
            sql=MALFORMED,
            regenerate=regenerate,
            revalidate=accept_all,
            mode=MODE_ENFORCE,
        )

        self.assertTrue(decision.blocked)
        self.assertEqual(
            regenerate.count, 0, "a hard failure must not be retried"
        )

    def test_missing_plan_fails_closed_in_enforce(self):
        decision = guard_sql(
            plan=None,
            sql=CORRECT_SQL,
            regenerate=Spy(result=CORRECT_SQL),
            revalidate=accept_all,
            mode=MODE_ENFORCE,
        )

        self.assertTrue(decision.blocked)

    def test_empty_regeneration_is_blocked(self):
        for empty in [None, "", "   "]:
            with self.subTest(value=repr(empty)):
                decision = guard_sql(
                    plan=self.plan,
                    sql=WRONG_AGG,
                    regenerate=lambda feedback: empty,
                    revalidate=accept_all,
                    mode=MODE_ENFORCE,
                )

                self.assertTrue(decision.blocked)

    def test_regeneration_raising_is_blocked(self):
        def explode(feedback):
            raise RuntimeError("provider unavailable")

        decision = guard_sql(
            plan=self.plan,
            sql=WRONG_AGG,
            regenerate=explode,
            revalidate=accept_all,
            mode=MODE_ENFORCE,
        )

        self.assertTrue(decision.blocked)

    def test_missing_callables_fail_closed(self):
        decision = guard_sql(
            plan=self.plan,
            sql=WRONG_AGG,
            mode=MODE_ENFORCE,
        )

        self.assertTrue(decision.blocked)

    def test_original_plan_is_used_for_the_recheck(self):
        """
        The retry must be judged against the plan the SQL was meant to
        implement. If the recheck used a freshly built plan, a query could pass
        because the plan moved rather than because the SQL was corrected.
        """

        seen = []

        original_plan = self.plan

        def regenerate(feedback):
            return WRONG_VALUE

        decision = guard_sql(
            plan=original_plan,
            sql=WRONG_AGG,
            regenerate=regenerate,
            revalidate=accept_all,
            mode=MODE_ENFORCE,
        )

        # WRONG_VALUE violates the ORIGINAL plan's filter, which is the only
        # way this can be detected.
        self.assertTrue(decision.blocked)
        self.assertIn(
            ViolationCode.FILTER_VALUE_MISMATCH.value,
            decision.final_result.codes(),
        )


# ---------------------------------------------------------------------------
# The database must never be reached on a blocked query
# ---------------------------------------------------------------------------

class TestDatabaseIsNeverCalled(unittest.TestCase):
    """
    Mirrors app.py's sequence: validate, guard, then execute. The spy stands in
    for the database connection and must never be invoked when the guard
    blocks.
    """

    def setUp(self):
        self.plan = plan_sum_cy_tamil_nadu()
        self.execute = Spy(result=[])

    def _run(self, sql, regenerate, revalidate=accept_all):
        """The ordering app.py performs."""

        decision = guard_sql(
            plan=self.plan,
            sql=sql,
            regenerate=regenerate,
            revalidate=revalidate,
            mode=MODE_ENFORCE,
        )

        if decision.blocked:
            return decision

        self.execute(decision.sql)
        return decision

    def test_violation_then_failed_retry_never_executes(self):
        decision = self._run(WRONG_AGG, lambda f: WRONG_VALUE)

        self.assertTrue(decision.blocked)
        self.assertEqual(self.execute.count, 0)

    def test_hard_failure_never_executes(self):
        decision = self._run(MALFORMED, Spy(result=CORRECT_SQL))

        self.assertTrue(decision.blocked)
        self.assertEqual(self.execute.count, 0)

    def test_regenerated_sql_failing_validation_never_executes(self):
        decision = self._run(
            WRONG_AGG,
            lambda f: "SELECT SUM(CY) FROM Ghost",
            revalidate=reject_all,
        )

        self.assertTrue(decision.blocked)
        self.assertEqual(self.execute.count, 0)

    def test_missing_plan_never_executes(self):
        decision = guard_sql(
            plan=None,
            sql=CORRECT_SQL,
            regenerate=Spy(result=CORRECT_SQL),
            revalidate=accept_all,
            mode=MODE_ENFORCE,
        )

        if not decision.blocked:
            self.execute(decision.sql)

        self.assertTrue(decision.blocked)
        self.assertEqual(self.execute.count, 0)

    def test_successful_retry_executes_the_regenerated_sql(self):
        decision = self._run(WRONG_AGG, lambda f: CORRECT_SQL)

        self.assertFalse(decision.blocked)
        self.assertEqual(self.execute.count, 1)
        self.assertEqual(self.execute.calls[0][0][0], CORRECT_SQL)

    def test_conforming_sql_executes_unchanged(self):
        decision = self._run(CORRECT_SQL, Spy())

        self.assertEqual(self.execute.count, 1)
        self.assertEqual(self.execute.calls[0][0][0], CORRECT_SQL)


# ---------------------------------------------------------------------------
# Feedback and determinism
# ---------------------------------------------------------------------------

class TestFeedback(unittest.TestCase):

    def test_feedback_names_expected_and_generated(self):
        result = verify_sql_against_plan(plan_sum_cy_tamil_nadu(), WRONG_AGG)

        feedback = format_guard_feedback(result)

        self.assertIn("PLAN CONFORMANCE FAILURE", feedback)
        self.assertIn("SUM(CY)", feedback)
        self.assertIn("AVG(CY)", feedback)
        self.assertIn("AGGREGATION_MISMATCH", feedback)

    def test_feedback_excludes_warnings(self):
        plan = plan_sum_cy_tamil_nadu()

        result = verify_sql_against_plan(
            plan,
            f"SELECT SUM(CY), PY FROM {SALES} WHERE State1 = 'Karnataka'",
        )

        feedback = format_guard_feedback(result)

        self.assertIn(ViolationCode.FILTER_VALUE_MISMATCH.value, feedback)
        self.assertNotIn(ViolationCode.UNEXPECTED_SELECTION.value, feedback)


class TestDeterminism(unittest.TestCase):

    def test_same_inputs_give_same_decision(self):
        plan = plan_sum_cy_tamil_nadu()

        first = guard_sql(plan=plan, sql=WRONG_VALUE, mode=MODE_SHADOW)

        for _ in range(20):
            again = guard_sql(plan=plan, sql=WRONG_VALUE, mode=MODE_SHADOW)

            self.assertEqual(again.codes(), first.codes())
            self.assertEqual(again.blocked, first.blocked)
            self.assertEqual(
                again.first_result.severity, first.first_result.severity
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
