"""
Gate 5 Step 30 - tests for the SQL Guard skeleton.

Step 30 has no conformance rules, so these tests prove exactly two things:

    1. A real semantic plan plus parseable SQL produces a structured PASS with
       the SQL metadata attached.
    2. Anything the guard cannot verify - unparseable SQL, blank SQL, a missing
       plan - fails closed as HARD_FAILURE.

The mutation tests that prove the guard catches hallucinated SQL (SUM changed
to AVG, the wrong filter value, a missing GROUP BY) belong to Step 31, once the
rules exist. One test below deliberately pins the current absence of those
rules so that Step 31 has a failing assertion to flip.

Plan fixtures use the real table and column names already used by the existing
plan tests, so the guard is exercised against the genuine SemanticPlan
contract rather than an invented one.
"""

import os
import sys
import unittest

# Adjust Python path to resolve the 'ai' and 'semantic' packages from backend.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai.guard import (
    GuardResult,
    Severity,
    Violation,
    ViolationCode,
    resolve_severity,
    verify_sql_against_plan,
)

from semantic.models.semantic_plan import (
    FilterOperator,
    RankDirection,
    RankMeasure,
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


SALES_TABLE = "QB_MDJMD_SALES_5YRS_SUMMARY"


def build_sales_plan() -> SemanticPlan:
    """
    A realistic plan: total current-year sales broken down by state.

    Mirrors the construction used in the existing semantic plan tests.
    """

    metric = SemanticMetric(
        metric_name="cy",
        business_name="Sales",
        table_name=SALES_TABLE,
        column_name="CY",
        aggregation_type="SUM",
    )

    dimension = SemanticDimension(
        dimension_name="state",
        business_name="State",
        table_name=SALES_TABLE,
        column_name="State1",
    )

    return SemanticPlan(
        intent=SemanticIntent.AGGREGATE,
        metrics=[metric],
        dimensions=[dimension],
        primary_table=SALES_TABLE,
        query_shape=SemanticQueryShape.SINGLE_VALUE,
    )


CONFORMING_SQL = f"""
    SELECT State1, SUM(CY) AS TotalSales
    FROM {SALES_TABLE}
    GROUP BY State1
"""


def build_filtered_plan() -> SemanticPlan:
    """
    The Batch A reference plan: total current-year sales for one state.

        SUM(CY) WHERE State1 = 'Tamil Nadu'

    Every mutation test below starts from this plan and CORRECT_FILTERED_SQL,
    then changes exactly one thing.
    """

    return SemanticPlan(
        intent=SemanticIntent.AGGREGATE,
        metrics=[
            SemanticMetric(
                metric_name="cy",
                business_name="Sales",
                table_name=SALES_TABLE,
                column_name="CY",
                aggregation_type="SUM",
            )
        ],
        filters=[
            SemanticFilter(
                dimension_name="state",
                table_name=SALES_TABLE,
                column_name="State1",
                operator=FilterOperator.EQUAL,
                values=["Tamil Nadu"],
            )
        ],
        primary_table=SALES_TABLE,
        query_shape=SemanticQueryShape.SINGLE_VALUE,
    )


CORRECT_FILTERED_SQL = f"""
    SELECT SUM(CY)
    FROM {SALES_TABLE}
    WHERE State1 = 'Tamil Nadu'
"""


def build_ranked_plan() -> SemanticPlan:
    """
    The Batch B reference plan: the five highest-selling states.

        TOP 5, SUM(CY) grouped by State1, ranked descending

    Exercises grouping, row limit and sort direction together, which is how
    they appear in a real ranking question.
    """

    return SemanticPlan(
        intent=SemanticIntent.AGGREGATE,
        metrics=[
            SemanticMetric(
                metric_name="cy",
                business_name="Sales",
                table_name=SALES_TABLE,
                column_name="CY",
                aggregation_type="SUM",
            )
        ],
        dimensions=[
            SemanticDimension(
                dimension_name="state",
                business_name="State",
                table_name=SALES_TABLE,
                column_name="State1",
            )
        ],
        ranking=SemanticRanking(
            top_n=5,
            direction=RankDirection.DESC,
            measure=RankMeasure.ABSOLUTE,
        ),
        primary_table=SALES_TABLE,
        query_shape=SemanticQueryShape.RANKED_LIST,
    )


CORRECT_RANKED_SQL = f"""
    SELECT TOP 5 State1, SUM(CY) AS TotalSales
    FROM {SALES_TABLE}
    GROUP BY State1
    ORDER BY SUM(CY) DESC
"""


STATE_TABLE = "DimState"


def build_joined_plan() -> SemanticPlan:
    """
    The Batch C reference plan: sales joined to a state dimension.

        SUM(CY) with SALES.StateKey = DimState.StateKey
    """

    return SemanticPlan(
        intent=SemanticIntent.AGGREGATE,
        metrics=[
            SemanticMetric(
                metric_name="cy",
                business_name="Sales",
                table_name=SALES_TABLE,
                column_name="CY",
                aggregation_type="SUM",
            )
        ],
        joins=[
            SemanticJoin(
                source_table=SALES_TABLE,
                source_key="StateKey",
                target_table=STATE_TABLE,
                target_key="StateKey",
            )
        ],
        primary_table=SALES_TABLE,
        relevant_tables=[
            SemanticTable(table_name=SALES_TABLE),
            SemanticTable(table_name=STATE_TABLE),
        ],
        query_shape=SemanticQueryShape.SINGLE_VALUE,
    )


CORRECT_JOINED_SQL = f"""
    SELECT SUM(s.CY)
    FROM {SALES_TABLE} s
    JOIN {STATE_TABLE} d ON s.StateKey = d.StateKey
"""


def _find(case, result, code):
    """Return the violation with the given code, or fail the test."""

    for violation in result.violations:
        if violation.code == code:
            return violation

    case.fail(f"expected violation {code.value}, got {result.codes()}")


class TestGuardHappyPath(unittest.TestCase):
    """A real plan plus SQL that parses produces a structured PASS."""

    def setUp(self):
        self.plan = build_sales_plan()

    def test_conforming_sql_passes(self):
        result = verify_sql_against_plan(self.plan, CONFORMING_SQL)

        self.assertIsInstance(result, GuardResult)
        self.assertTrue(result.passed)
        self.assertEqual(result.severity, Severity.PASS)
        self.assertEqual(result.violations, [])
        self.assertFalse(result.blocked)

    def test_result_carries_parsed_sql(self):
        result = verify_sql_against_plan(self.plan, CONFORMING_SQL)

        self.assertEqual(result.sql, CONFORMING_SQL)
        self.assertIsNotNone(result.serialized_sql)
        self.assertIn("SUM", result.serialized_sql.upper())

    def test_result_carries_extracted_metadata(self):
        """
        Proves the guard reuses the existing metadata extractor rather than
        doing its own parsing - the Step 31 rules read these fields.
        """

        result = verify_sql_against_plan(self.plan, CONFORMING_SQL)

        self.assertIsNotNone(result.metadata)

        table_names = [t.name.upper() for t in result.metadata.tables]
        self.assertIn(SALES_TABLE.upper(), table_names)

        aggregate_functions = [
            a.function.upper() for a in result.metadata.aggregates
        ]
        self.assertIn("SUM", aggregate_functions)

    def test_simple_select_passes(self):
        """
        A plan asking only for a dimension is satisfied by a plain SELECT.

        Uses a metric-free plan deliberately: once the Batch A rules exist,
        selecting a dimension while the plan also demands SUM(CY) is correctly
        a MISSING_METRIC violation, which is covered in TestMetricRules.
        """

        dimension_only_plan = SemanticPlan(
            intent=SemanticIntent.AGGREGATE,
            dimensions=[
                SemanticDimension(
                    dimension_name="state",
                    business_name="State",
                    table_name=SALES_TABLE,
                    column_name="State1",
                )
            ],
            primary_table=SALES_TABLE,
        )

        result = verify_sql_against_plan(
            dimension_only_plan,
            f"SELECT State1 FROM {SALES_TABLE}",
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.severity, Severity.PASS)

    def test_unrequested_top_is_now_reported(self):
        """
        The same query with TOP 10 is no longer accepted. The plan requested no
        ranking, so a row limit answers a narrower question than was asked.
        This behaviour was added when UNEXPECTED_LIMIT closed that gap.
        """

        dimension_only_plan = SemanticPlan(
            dimensions=[
                SemanticDimension(
                    dimension_name="state",
                    business_name="State",
                    table_name=SALES_TABLE,
                    column_name="State1",
                )
            ],
            primary_table=SALES_TABLE,
        )

        result = verify_sql_against_plan(
            dimension_only_plan,
            f"SELECT TOP 10 State1 FROM {SALES_TABLE}",
        )

        self.assertIn(ViolationCode.UNEXPECTED_LIMIT.value, result.codes())


class TestGuardFailsClosed(unittest.TestCase):
    """Anything the guard cannot verify must block, never pass by default."""

    def setUp(self):
        self.plan = build_sales_plan()

    def test_malformed_sql_is_hard_failure(self):
        result = verify_sql_against_plan(self.plan, "SELECT FROM WHERE")

        self.assertFalse(result.passed)
        self.assertEqual(result.severity, Severity.HARD_FAILURE)
        self.assertTrue(result.blocked)
        self.assertEqual(result.codes(), [ViolationCode.SQL_PARSE_FAILURE.value])
        self.assertIsNone(result.metadata)

    def test_various_unparseable_sql_all_hard_fail(self):
        for sql in [
            "SELECT FROM WHERE",
            "SELECT * FROM",
            "this is not sql at all",
            "SELECT (((",
            "SELECT 1 +",
        ]:
            with self.subTest(sql=sql):
                result = verify_sql_against_plan(self.plan, sql)

                self.assertEqual(result.severity, Severity.HARD_FAILURE)
                self.assertIn(
                    ViolationCode.SQL_PARSE_FAILURE.value,
                    result.codes(),
                )

    def test_blank_sql_is_hard_failure(self):
        for sql in ["", "   ", "\n\t "]:
            with self.subTest(sql=repr(sql)):
                result = verify_sql_against_plan(self.plan, sql)

                self.assertEqual(result.severity, Severity.HARD_FAILURE)
                self.assertEqual(result.codes(), [ViolationCode.EMPTY_SQL.value])

    def test_none_sql_is_hard_failure(self):
        result = verify_sql_against_plan(self.plan, None)

        self.assertEqual(result.severity, Severity.HARD_FAILURE)
        self.assertEqual(result.codes(), [ViolationCode.EMPTY_SQL.value])

    def test_missing_plan_is_hard_failure(self):
        """
        The guard must refuse when there is no plan, not approve. Passing here
        would silently bless every query on a code path that forgot the plan.
        """

        result = verify_sql_against_plan(None, CONFORMING_SQL)

        self.assertFalse(result.passed)
        self.assertEqual(result.severity, Severity.HARD_FAILURE)
        self.assertTrue(result.blocked)
        self.assertEqual(result.codes(), [ViolationCode.MISSING_PLAN.value])

    def test_violation_message_is_readable(self):
        result = verify_sql_against_plan(self.plan, "SELECT FROM WHERE")

        message = str(result.violations[0])

        self.assertIn(ViolationCode.SQL_PARSE_FAILURE.value, message)
        self.assertTrue(len(message) > 20)


class TestSeverityResolution(unittest.TestCase):
    """The strongest severity present decides the result."""

    def _violation(self, severity: Severity) -> Violation:
        return Violation(
            code=ViolationCode.SQL_PARSE_FAILURE,
            severity=severity,
            message="test",
        )

    def test_no_violations_is_pass(self):
        self.assertEqual(resolve_severity([]), Severity.PASS)

    def test_single_violation_wins(self):
        self.assertEqual(
            resolve_severity([self._violation(Severity.WARNING)]),
            Severity.WARNING,
        )

    def test_strongest_severity_wins(self):
        violations = [
            self._violation(Severity.WARNING),
            self._violation(Severity.HARD_FAILURE),
            self._violation(Severity.WARNING),
        ]

        self.assertEqual(resolve_severity(violations), Severity.HARD_FAILURE)

    def test_repairable_outranks_warning(self):
        violations = [
            self._violation(Severity.WARNING),
            self._violation(Severity.REPAIRABLE_FAILURE),
        ]

        self.assertEqual(
            resolve_severity(violations),
            Severity.REPAIRABLE_FAILURE,
        )


class TestStep31RulesNowCatchContradictions(unittest.TestCase):
    """
    The inversion of the Step 30 scope-boundary test.

    Step 30 recorded that contradicting SQL passed because no rules existed.
    Batch A is exactly the change that makes it fail, so this asserts the
    opposite of what it asserted before.
    """

    def test_contradicting_sql_is_now_caught(self):
        plan = build_filtered_plan()  # SUM(CY) WHERE State1 = 'Tamil Nadu'

        contradicting_sql = f"""
            SELECT AVG(PY) AS Wrong
            FROM {SALES_TABLE}
            WHERE State1 = 'Karnataka'
        """

        result = verify_sql_against_plan(plan, contradicting_sql)

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.METRIC_MISMATCH.value, result.codes())
        self.assertIn(ViolationCode.FILTER_VALUE_MISMATCH.value, result.codes())


class TestMetricRules(unittest.TestCase):
    """Rule 1 (metric column) and Rule 2 (aggregation)."""

    def setUp(self):
        self.plan = build_filtered_plan()

    def test_correct_metric_and_aggregation_passes(self):
        result = verify_sql_against_plan(self.plan, CORRECT_FILTERED_SQL)

        self.assertTrue(result.passed)
        self.assertEqual(result.violations, [])

    def test_wrong_metric_column_is_caught(self):
        """MUTATION: SUM(CY) -> SUM(PY). A plausible number from the wrong column."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(PY) FROM {SALES_TABLE} WHERE State1 = 'Tamil Nadu'",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.METRIC_MISMATCH.value, result.codes())

        violation = self._find(result, ViolationCode.METRIC_MISMATCH)
        self.assertEqual(violation.expected, "CY")
        self.assertIn("PY", violation.actual)
        self.assertEqual(violation.severity, Severity.REPAIRABLE_FAILURE)

    def test_wrong_aggregation_is_caught(self):
        """MUTATION: SUM(CY) -> AVG(CY). Right column, wrong arithmetic."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT AVG(CY) FROM {SALES_TABLE} WHERE State1 = 'Tamil Nadu'",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.AGGREGATION_MISMATCH.value, result.codes())

        violation = self._find(result, ViolationCode.AGGREGATION_MISMATCH)
        self.assertEqual(violation.expected, "SUM(CY)")
        self.assertEqual(violation.actual, "AVG(CY)")

    def test_other_aggregations_are_caught(self):
        for function in ["AVG", "MIN", "MAX", "COUNT"]:
            with self.subTest(function=function):
                result = verify_sql_against_plan(
                    self.plan,
                    f"SELECT {function}(CY) FROM {SALES_TABLE} "
                    "WHERE State1 = 'Tamil Nadu'",
                )

                self.assertIn(
                    ViolationCode.AGGREGATION_MISMATCH.value,
                    result.codes(),
                )

    def test_missing_metric_is_caught(self):
        """MUTATION: the metric column is absent from the query entirely."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT State1 FROM {SALES_TABLE} WHERE State1 = 'Tamil Nadu'",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.MISSING_METRIC.value, result.codes())

    def test_unaggregated_metric_is_caught(self):
        """MUTATION: the right column selected raw, with no SUM applied."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT CY FROM {SALES_TABLE} WHERE State1 = 'Tamil Nadu'",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.AGGREGATION_MISMATCH.value, result.codes())

    def _find(self, result, code):
        for violation in result.violations:
            if violation.code == code:
                return violation

        self.fail(f"expected violation {code.value}, got {result.codes()}")


class TestFilterRules(unittest.TestCase):
    """Rules 3 (filter column), 4 (filter value) and 5 (missing filter)."""

    def setUp(self):
        self.plan = build_filtered_plan()

    def test_correct_filter_passes(self):
        result = verify_sql_against_plan(self.plan, CORRECT_FILTERED_SQL)

        self.assertTrue(result.passed)

    def test_wrong_filter_value_is_caught(self):
        """
        MUTATION: Tamil Nadu -> Karnataka.

        The most dangerous mutation in the suite. The query runs, the number
        looks entirely reasonable, and it is the wrong state.
        """

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(CY) FROM {SALES_TABLE} WHERE State1 = 'Karnataka'",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.FILTER_VALUE_MISMATCH.value, result.codes())

        violation = self._find(result, ViolationCode.FILTER_VALUE_MISMATCH)
        self.assertIn("tamil nadu", violation.expected.lower())
        self.assertIn("karnataka", violation.actual.lower())

    def test_missing_required_filter_is_caught(self):
        """MUTATION: filter removed. Returns the whole country."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(CY) FROM {SALES_TABLE}",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.MISSING_FILTER.value, result.codes())

    def test_wrong_filter_column_is_caught(self):
        """
        MUTATION: filters MktType instead of State1.

        Reported as two precise facts - the required filter is absent, and an
        unrequested one is present - rather than inferring that one replaced
        the other, which would be a guess.
        """

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(CY) FROM {SALES_TABLE} WHERE MktType = 'DIRECT'",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.MISSING_FILTER.value, result.codes())
        self.assertIn(ViolationCode.UNEXPECTED_FILTER.value, result.codes())

    def test_extra_filter_is_caught(self):
        """
        MUTATION: the required filter is kept but another is added.

        An extra filter changes which rows are counted, so it is an error and
        not a note.
        """

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(CY) FROM {SALES_TABLE} "
            "WHERE State1 = 'Tamil Nadu' AND MktType = 'DIRECT'",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.UNEXPECTED_FILTER.value, result.codes())

    def test_inverted_operator_is_caught(self):
        """MUTATION: '=' becomes '!=' - the filter now excludes the target."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(CY) FROM {SALES_TABLE} WHERE State1 != 'Tamil Nadu'",
        )

        self.assertFalse(result.passed)
        self.assertIn(
            ViolationCode.FILTER_OPERATOR_MISMATCH.value,
            result.codes(),
        )

    def _find(self, result, code):
        for violation in result.violations:
            if violation.code == code:
                return violation

        self.fail(f"expected violation {code.value}, got {result.codes()}")


class TestNoFalsePositives(unittest.TestCase):
    """
    Correct SQL written in different but equivalent ways must pass.

    A guard that flags legitimate queries gets switched off, so these matter
    as much as the mutation tests.
    """

    def setUp(self):
        self.plan = build_filtered_plan()

    def test_table_qualified_columns_pass(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(s.CY) FROM {SALES_TABLE} s WHERE s.State1 = 'Tamil Nadu'",
        )

        self.assertTrue(result.passed, result.codes())

    def test_lowercase_columns_pass(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(cy) FROM {SALES_TABLE} WHERE state1 = 'Tamil Nadu'",
        )

        self.assertTrue(result.passed, result.codes())

    def test_lowercase_aggregation_passes(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT sum(CY) FROM {SALES_TABLE} WHERE State1 = 'Tamil Nadu'",
        )

        self.assertTrue(result.passed, result.codes())

    def test_filter_value_case_is_ignored(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(CY) FROM {SALES_TABLE} WHERE State1 = 'tamil nadu'",
        )

        self.assertTrue(result.passed, result.codes())

    def test_in_with_single_value_matches_equality(self):
        """
        "State1 IN ('Tamil Nadu')" is the same restriction as "= 'Tamil Nadu'".
        Treating them as different would be a false violation.
        """

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(CY) FROM {SALES_TABLE} WHERE State1 IN ('Tamil Nadu')",
        )

        self.assertTrue(result.passed, result.codes())

    def test_aliased_metric_passes(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(CY) AS TotalSales FROM {SALES_TABLE} "
            "WHERE State1 = 'Tamil Nadu'",
        )

        self.assertTrue(result.passed, result.codes())

    def test_join_condition_is_not_read_as_a_filter(self):
        """
        A JOIN ... ON clause is not a filter. Reading it as one would make
        every joined query report an unexpected filter.
        """

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(s.CY) FROM {SALES_TABLE} s "
            "JOIN DimState d ON s.StateKey = d.StateKey "
            "WHERE s.State1 = 'Tamil Nadu'",
        )

        self.assertNotIn(ViolationCode.UNEXPECTED_FILTER.value, result.codes())


class TestExtraSelections(unittest.TestCase):
    """Extra selected columns are a note, not a block."""

    def test_extra_selected_column_is_a_warning_only(self):
        plan = build_filtered_plan()

        result = verify_sql_against_plan(
            plan,
            f"SELECT SUM(CY), PY FROM {SALES_TABLE} WHERE State1 = 'Tamil Nadu'",
        )

        self.assertIn(ViolationCode.UNEXPECTED_SELECTION.value, result.codes())
        self.assertEqual(result.severity, Severity.WARNING)
        self.assertTrue(result.passed)
        self.assertFalse(result.blocked)


class TestViolationsAreStructured(unittest.TestCase):
    """Every violation must say what was expected and what was found."""

    def test_violation_carries_expected_and_actual(self):
        plan = build_filtered_plan()

        result = verify_sql_against_plan(
            plan,
            f"SELECT AVG(CY) FROM {SALES_TABLE} WHERE State1 = 'Karnataka'",
        )

        self.assertEqual(len(result.violations), 2)

        for violation in result.violations:
            self.assertIsNotNone(violation.expected)
            self.assertIsNotNone(violation.actual)
            self.assertTrue(len(violation.message) > 20)
            self.assertIsInstance(violation.code, ViolationCode)

    def test_all_violations_reported_not_just_the_first(self):
        """A reviewer fixing SQL needs the whole list, not one error at a time."""

        plan = build_filtered_plan()

        result = verify_sql_against_plan(
            plan,
            f"SELECT AVG(PY) FROM {SALES_TABLE} WHERE MktType = 'DIRECT'",
        )

        codes = result.codes()

        self.assertIn(ViolationCode.METRIC_MISMATCH.value, codes)
        self.assertIn(ViolationCode.MISSING_FILTER.value, codes)
        self.assertIn(ViolationCode.UNEXPECTED_FILTER.value, codes)


class TestGroupingRules(unittest.TestCase):
    """Batch B - the figures must be broken down the way the plan asked."""

    def setUp(self):
        self.plan = build_ranked_plan()

    def test_correct_grouping_passes(self):
        result = verify_sql_against_plan(self.plan, CORRECT_RANKED_SQL)

        self.assertEqual(result.violations, [], result.codes())
        self.assertTrue(result.passed)

    def test_wrong_grouping_column_is_caught(self):
        """MUTATION: GROUP BY State1 -> GROUP BY MktType."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT TOP 5 MktType, SUM(CY) FROM {SALES_TABLE} "
            "GROUP BY MktType ORDER BY SUM(CY) DESC",
        )

        codes = result.codes()

        self.assertIn(ViolationCode.MISSING_GROUPING.value, codes)
        self.assertIn(ViolationCode.UNEXPECTED_GROUPING.value, codes)

    def test_missing_grouping_is_caught(self):
        """MUTATION: GROUP BY dropped, so everything collapses to one total."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT TOP 5 SUM(CY) FROM {SALES_TABLE} ORDER BY SUM(CY) DESC",
        )

        self.assertIn(ViolationCode.MISSING_GROUPING.value, result.codes())

    def test_extra_grouping_is_caught(self):
        """MUTATION: an unrequested dimension added to the GROUP BY."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT TOP 5 State1, MktType, SUM(CY) FROM {SALES_TABLE} "
            "GROUP BY State1, MktType ORDER BY SUM(CY) DESC",
        )

        self.assertIn(ViolationCode.UNEXPECTED_GROUPING.value, result.codes())

    def test_grouping_violations_are_warnings_not_blocks(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT TOP 5 State1, MktType, SUM(CY) FROM {SALES_TABLE} "
            "GROUP BY State1, MktType ORDER BY SUM(CY) DESC",
        )

        self.assertEqual(result.severity, Severity.WARNING)
        self.assertFalse(result.blocked)

    def test_grouping_not_required_without_aggregation(self):
        """
        A plain SELECT of a dimension needs no GROUP BY. Demanding one here
        would be a false violation.
        """

        plan = SemanticPlan(
            dimensions=[
                SemanticDimension(
                    dimension_name="state",
                    business_name="State",
                    table_name=SALES_TABLE,
                    column_name="State1",
                )
            ],
            primary_table=SALES_TABLE,
        )

        result = verify_sql_against_plan(
            plan,
            f"SELECT State1 FROM {SALES_TABLE}",
        )

        self.assertNotIn(ViolationCode.MISSING_GROUPING.value, result.codes())

    def test_qualified_group_by_column_passes(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT TOP 5 s.State1, SUM(s.CY) FROM {SALES_TABLE} s "
            "GROUP BY s.State1 ORDER BY SUM(s.CY) DESC",
        )

        self.assertNotIn(ViolationCode.MISSING_GROUPING.value, result.codes())
        self.assertNotIn(ViolationCode.UNEXPECTED_GROUPING.value, result.codes())


class TestRowLimitRules(unittest.TestCase):
    """Batch B - TOP / row limit."""

    def setUp(self):
        self.plan = build_ranked_plan()  # top_n = 5

    def test_correct_limit_passes(self):
        result = verify_sql_against_plan(self.plan, CORRECT_RANKED_SQL)

        self.assertNotIn(ViolationCode.LIMIT_MISMATCH.value, result.codes())

    def test_wrong_limit_is_caught(self):
        """MUTATION: TOP 5 -> TOP 50."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT TOP 50 State1, SUM(CY) FROM {SALES_TABLE} "
            "GROUP BY State1 ORDER BY SUM(CY) DESC",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.LIMIT_MISMATCH.value, result.codes())

        violation = _find(self, result, ViolationCode.LIMIT_MISMATCH)
        self.assertEqual(violation.expected, "TOP 5")
        self.assertEqual(violation.actual, "TOP 50")

    def test_missing_limit_is_caught(self):
        """MUTATION: TOP removed, so the whole result set returns."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT State1, SUM(CY) FROM {SALES_TABLE} "
            "GROUP BY State1 ORDER BY SUM(CY) DESC",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.MISSING_LIMIT.value, result.codes())

    def test_offset_fetch_is_recognised_as_a_limit(self):
        """
        T-SQL can cap rows with OFFSET ... FETCH instead of TOP. The metadata
        extractor reports no limit for that form, so reading it only from
        metadata would raise a false MISSING_LIMIT.
        """

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT State1, SUM(CY) FROM {SALES_TABLE} GROUP BY State1 "
            "ORDER BY SUM(CY) DESC OFFSET 0 ROWS FETCH NEXT 5 ROWS ONLY",
        )

        self.assertNotIn(ViolationCode.MISSING_LIMIT.value, result.codes())
        self.assertNotIn(ViolationCode.LIMIT_MISMATCH.value, result.codes())

    def test_offset_fetch_with_wrong_count_is_caught(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT State1, SUM(CY) FROM {SALES_TABLE} GROUP BY State1 "
            "ORDER BY SUM(CY) DESC OFFSET 0 ROWS FETCH NEXT 50 ROWS ONLY",
        )

        self.assertIn(ViolationCode.LIMIT_MISMATCH.value, result.codes())

    def test_no_ranking_in_plan_means_no_limit_checks(self):
        plan = build_filtered_plan()  # no ranking at all

        result = verify_sql_against_plan(
            plan,
            f"SELECT TOP 99 SUM(CY) FROM {SALES_TABLE} WHERE State1 = 'Tamil Nadu'",
        )

        self.assertNotIn(ViolationCode.LIMIT_MISMATCH.value, result.codes())
        self.assertNotIn(ViolationCode.MISSING_LIMIT.value, result.codes())


class TestOrderDirectionRules(unittest.TestCase):
    """Batch B - sort direction. Getting this wrong inverts the answer."""

    def setUp(self):
        self.plan = build_ranked_plan()  # direction = DESC

    def test_correct_direction_passes(self):
        result = verify_sql_against_plan(self.plan, CORRECT_RANKED_SQL)

        self.assertNotIn(
            ViolationCode.ORDER_DIRECTION_MISMATCH.value,
            result.codes(),
        )

    def test_inverted_direction_is_caught(self):
        """
        MUTATION: DESC -> ASC.

        'Top 5 by sales' becomes 'bottom 5 by sales'. The query runs, returns
        five rows, and answers the opposite question.
        """

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT TOP 5 State1, SUM(CY) FROM {SALES_TABLE} "
            "GROUP BY State1 ORDER BY SUM(CY) ASC",
        )

        self.assertFalse(result.passed)
        self.assertIn(
            ViolationCode.ORDER_DIRECTION_MISMATCH.value,
            result.codes(),
        )

        violation = _find(self, result, ViolationCode.ORDER_DIRECTION_MISMATCH)
        self.assertIn("DESC", violation.expected)
        self.assertIn("ASC", violation.actual)

    def test_omitted_direction_is_caught_as_ascending(self):
        """
        'ORDER BY x' with no direction is ascending in SQL. When the plan asks
        for descending, that is a genuine inversion, not a formatting detail.
        """

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT TOP 5 State1, SUM(CY) FROM {SALES_TABLE} "
            "GROUP BY State1 ORDER BY SUM(CY)",
        )

        self.assertIn(
            ViolationCode.ORDER_DIRECTION_MISMATCH.value,
            result.codes(),
        )

    def test_missing_order_by_is_caught(self):
        """
        MUTATION: ORDER BY removed while TOP remains.

        TOP N without ORDER BY returns an arbitrary N rows - the same query can
        give a different answer on each run.
        """

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT TOP 5 State1, SUM(CY) FROM {SALES_TABLE} GROUP BY State1",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.MISSING_ORDER_BY.value, result.codes())

    def test_ordering_by_alias_still_checks_direction(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT TOP 5 State1, SUM(CY) AS Total FROM {SALES_TABLE} "
            "GROUP BY State1 ORDER BY Total DESC",
        )

        self.assertNotIn(
            ViolationCode.ORDER_DIRECTION_MISMATCH.value,
            result.codes(),
        )

    def test_no_direction_in_plan_means_no_order_checks(self):
        plan = build_filtered_plan()

        result = verify_sql_against_plan(
            plan,
            f"SELECT SUM(CY) FROM {SALES_TABLE} WHERE State1 = 'Tamil Nadu'",
        )

        self.assertNotIn(ViolationCode.MISSING_ORDER_BY.value, result.codes())


class TestJoinRules(unittest.TestCase):
    """Batch C - the tables must be connected the way the plan requires."""

    def setUp(self):
        self.plan = build_joined_plan()

    def test_correct_join_passes(self):
        result = verify_sql_against_plan(self.plan, CORRECT_JOINED_SQL)

        self.assertEqual(result.violations, [], result.codes())
        self.assertTrue(result.passed)

    def test_unaliased_join_passes(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM({SALES_TABLE}.CY) FROM {SALES_TABLE} "
            f"JOIN {STATE_TABLE} "
            f"ON {SALES_TABLE}.StateKey = {STATE_TABLE}.StateKey",
        )

        self.assertEqual(result.violations, [], result.codes())

    def test_reversed_join_order_passes(self):
        """
        'b.k = a.k' is the same relationship as 'a.k = b.k'. Treating the
        written order as significant would be a false violation.
        """

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(s.CY) FROM {SALES_TABLE} s JOIN {STATE_TABLE} d "
            "ON d.StateKey = s.StateKey",
        )

        self.assertEqual(result.violations, [], result.codes())

    def test_where_style_join_passes(self):
        """
        'FROM A, B WHERE A.k = B.k' is an ordinary join written in the older
        style. SQLMetadata reports no join columns for it, so reading only the
        ON clauses would call this a Cartesian product.
        """

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(s.CY) FROM {SALES_TABLE} s, {STATE_TABLE} d "
            "WHERE s.StateKey = d.StateKey",
        )

        self.assertNotIn(ViolationCode.CARTESIAN_JOIN.value, result.codes())
        self.assertNotIn(ViolationCode.JOIN_MISMATCH.value, result.codes())

    def test_wrong_join_key_is_caught(self):
        """MUTATION: right tables, wrong columns. Pairs the wrong rows."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(s.CY) FROM {SALES_TABLE} s JOIN {STATE_TABLE} d "
            "ON s.RegionKey = d.RegionKey",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.JOIN_KEY_MISMATCH.value, result.codes())

    def test_join_to_wrong_table_is_caught(self):
        """MUTATION: joined to a different table than the plan required."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(s.CY) FROM {SALES_TABLE} s JOIN DimProduct p "
            "ON s.ProductKey = p.ProductKey",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.JOIN_MISMATCH.value, result.codes())

    def test_missing_join_is_caught(self):
        """MUTATION: the required join is absent entirely."""

        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(CY) FROM {SALES_TABLE}",
        )

        self.assertFalse(result.passed)
        self.assertIn(ViolationCode.JOIN_MISMATCH.value, result.codes())


class TestCartesianDetection(unittest.TestCase):
    """
    Two or more tables with nothing linking them.

    The only HARD_FAILURE in Step 31: wrong regardless of the plan, and
    capable of exhausting the database on a large table.
    """

    def setUp(self):
        self.plan = build_joined_plan()

    def test_comma_join_without_condition_is_caught(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(s.CY) FROM {SALES_TABLE} s, {STATE_TABLE} d",
        )

        self.assertIn(ViolationCode.CARTESIAN_JOIN.value, result.codes())
        self.assertEqual(result.severity, Severity.HARD_FAILURE)
        self.assertTrue(result.blocked)

    def test_cross_join_is_caught(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(s.CY) FROM {SALES_TABLE} s CROSS JOIN {STATE_TABLE} d",
        )

        self.assertIn(ViolationCode.CARTESIAN_JOIN.value, result.codes())
        self.assertEqual(result.severity, Severity.HARD_FAILURE)

    def test_join_without_on_clause_is_caught(self):
        result = verify_sql_against_plan(
            self.plan,
            f"SELECT SUM(s.CY) FROM {SALES_TABLE} s JOIN {STATE_TABLE} d",
        )

        self.assertIn(ViolationCode.CARTESIAN_JOIN.value, result.codes())

    def test_single_table_is_never_cartesian(self):
        result = verify_sql_against_plan(
            build_filtered_plan(),
            f"SELECT SUM(CY) FROM {SALES_TABLE} WHERE State1 = 'Tamil Nadu'",
        )

        self.assertNotIn(ViolationCode.CARTESIAN_JOIN.value, result.codes())

    def test_properly_joined_query_is_never_cartesian(self):
        result = verify_sql_against_plan(self.plan, CORRECT_JOINED_SQL)

        self.assertNotIn(ViolationCode.CARTESIAN_JOIN.value, result.codes())


class TestUnexpectedTables(unittest.TestCase):
    """Tables the plan never mentioned are noted, not blocked."""

    def test_unexpected_table_is_a_warning(self):
        result = verify_sql_against_plan(
            build_joined_plan(),
            f"SELECT SUM(s.CY) FROM {SALES_TABLE} s "
            f"JOIN {STATE_TABLE} d ON s.StateKey = d.StateKey "
            "JOIN DimProduct p ON s.ProductKey = p.ProductKey",
        )

        self.assertIn(ViolationCode.UNEXPECTED_TABLE.value, result.codes())

        violation = _find(self, result, ViolationCode.UNEXPECTED_TABLE)
        self.assertEqual(violation.severity, Severity.WARNING)

    def test_declared_tables_are_not_reported(self):
        result = verify_sql_against_plan(build_joined_plan(), CORRECT_JOINED_SQL)

        self.assertNotIn(ViolationCode.UNEXPECTED_TABLE.value, result.codes())

    def test_plan_without_tables_reports_nothing(self):
        """
        A plan that declares no tables cannot say which are unexpected.
        Guessing would produce noise on every query.
        """

        plan = SemanticPlan()

        result = verify_sql_against_plan(
            plan,
            f"SELECT SUM(CY) FROM {SALES_TABLE}",
        )

        self.assertNotIn(ViolationCode.UNEXPECTED_TABLE.value, result.codes())


class TestDeterminism(unittest.TestCase):
    """
    Same input, same verdict, every time.

    This is the property that makes the guard testable at all, and the reason
    no model is used anywhere inside it.
    """

    def test_repeated_runs_are_identical(self):
        plan = build_filtered_plan()

        sql = f"SELECT AVG(PY) FROM {SALES_TABLE} WHERE State1 = 'Karnataka'"

        first = verify_sql_against_plan(plan, sql)
        results = [verify_sql_against_plan(plan, sql) for _ in range(25)]

        for result in results:
            self.assertEqual(result.codes(), first.codes())
            self.assertEqual(result.severity, first.severity)
            self.assertEqual(result.passed, first.passed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
