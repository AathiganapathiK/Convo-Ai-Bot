import unittest
import datetime
from semantic.temporal.models import TimeCapability, TimeSettings, YearRange
from semantic.temporal.enums import TimeStrategyType, CalendarType, TimeIntentType, StrategySelectionReason
from semantic.temporal.time_resolver import TimeResolver
from semantic.temporal.capability_cache import TimeResolutionCache
from semantic.temporal.models import LastNYearsIntent


class TestTimeResolver(unittest.TestCase):

    def setUp(self):
        self.resolver = TimeResolver()
        self.ref_date = datetime.date(2026, 8, 5)
        TimeResolutionCache.clear()

    def tearDown(self):
        TimeResolutionCache.clear()

    def test_end_to_end_question_resolution(self):
        # Scenario: "Show sales for the past 5 years" raw text resolution
        # Expect: Correct intent parsing, snapshot strategy chosen, and correct plan execution
        capability = TimeCapability(
            date_columns=["OrderDate"],
            snapshot_mapping={0: "CY", 1: "PY", 2: "PPY", 3: "PPPY", 4: "PPPPY"}
        )
        settings = TimeSettings()
        
        result = self.resolver.resolve(
            question="Show sales for the past 5 years",
            capability=capability,
            settings=settings,
            reference_date=self.ref_date
        )
        
        self.assertTrue(result.resolved)
        self.assertIsNotNone(result.intent)
        self.assertEqual(result.intent.intent_type, TimeIntentType.LAST_N_YEARS)
        self.assertIsNotNone(result.plan)
        self.assertEqual(result.plan.strategy, TimeStrategyType.SNAPSHOT)
        self.assertEqual(result.plan.snapshot_columns, ["CY", "PY", "PPY", "PPPY", "PPPPY"])
        self.assertFalse(result.is_partial)
        self.assertEqual(len(result.warnings), 0)

    def test_snapshot_path(self):
        # Explicit intent resolution for Snapshot strategy
        intent = LastNYearsIntent(count=3, reference_date=self.ref_date)
        capability = TimeCapability(
            date_columns=["OrderDate"],
            snapshot_mapping={0: "CY", 1: "PY", 2: "PPY"}
        )
        
        result = self.resolver.resolve_intent(intent, capability=capability)
        self.assertTrue(result.resolved)
        self.assertEqual(result.plan.strategy, TimeStrategyType.SNAPSHOT)
        self.assertEqual(result.plan.snapshot_columns, ["CY", "PY", "PPY"])

    def test_date_column_path(self):
        # Scenario: Last 30 days query, should use DATE_COLUMN strategy
        capability = TimeCapability(date_columns=["OrderDate"])
        
        result = self.resolver.resolve(
            question="Show sales for the last 30 days",
            capability=capability,
            reference_date=self.ref_date
        )
        
        self.assertTrue(result.resolved)
        self.assertEqual(result.plan.strategy, TimeStrategyType.DATE_COLUMN)
        self.assertEqual(result.plan.date_column, "OrderDate")
        # Assert start/end dates from the DateCalculator
        self.assertEqual(result.plan.start_date, datetime.date(2026, 7, 7))
        self.assertEqual(result.plan.end_date, datetime.date(2026, 8, 5))

    def test_fiscal_year_path(self):
        # Scenario: "Show fiscal YTD sales" with default fiscal calendar preference
        capability = TimeCapability(date_columns=["OrderDate"])
        settings = TimeSettings(default_calendar=CalendarType.FISCAL, financial_year_start_month=4)
        
        result = self.resolver.resolve(
            question="Show fiscal YTD sales",
            capability=capability,
            settings=settings,
            reference_date=self.ref_date
        )
        
        self.assertTrue(result.resolved)
        self.assertEqual(result.plan.strategy, TimeStrategyType.FISCAL)
        # FYTD starts on April 1st, 2026
        self.assertEqual(result.plan.start_date, datetime.date(2026, 4, 1))
        self.assertEqual(result.plan.end_date, self.ref_date)

    def test_calendar_dimension_path(self):
        # Scenario: Date range query with calendar table support but no snapshot mapping
        # This will force the selector to prioritize CALENDAR_DIMENSION (85) over DATE_COLUMN (70)
        capability = TimeCapability(
            date_columns=["OrderDate"],
            calendar_tables=["DimDate"]
        )
        settings = TimeSettings(default_calendar=CalendarType.CALENDAR)
        
        result = self.resolver.resolve(
            question="Show sales for the past 5 years",
            capability=capability,
            settings=settings,
            reference_date=self.ref_date
        )
        
        self.assertTrue(result.resolved)
        self.assertEqual(result.plan.strategy, TimeStrategyType.CALENDAR_DIMENSION)
        self.assertEqual(result.plan.calendar_table, "DimDate")
        self.assertEqual(result.plan.start_date, datetime.date(2022, 1, 1))
        self.assertEqual(result.plan.end_date, datetime.date(2026, 12, 31))

    def test_graceful_degradation_path(self):
        # Scenario: Request 5 years on snapshot only (no date columns to fallback on).
        # Should degrade snapshot to 2 years and add warning.
        intent = LastNYearsIntent(count=5, reference_date=self.ref_date)
        capability = TimeCapability(
            date_columns=[],
            snapshot_mapping={0: "CY", 1: "PY"}
        )
        
        result = self.resolver.resolve_intent(intent, capability=capability)
        self.assertTrue(result.resolved)
        self.assertEqual(result.plan.strategy, TimeStrategyType.SNAPSHOT)
        self.assertTrue(result.is_partial)
        self.assertEqual(result.plan.snapshot_columns, ["CY", "PY"])
        self.assertIn("only 2 years are available", result.warnings[0])

    def test_cache_hit_path(self):
        # Scenario: Repeated resolution with cache hit check
        conn_id = "test_conn_time_resolver"
        capability = TimeCapability(
            date_columns=["OrderDate"],
            snapshot_mapping={0: "CY", 1: "PY", 2: "PPY", 3: "PPPY", 4: "PPPPY"}
        )
        
        # Prime cache and verify first resolution
        res1 = self.resolver.resolve(
            question="Show sales for the past 5 years",
            capability=capability,
            connection_id=conn_id,
            reference_date=self.ref_date
        )
        self.assertTrue(res1.resolved)
        
        # Second call should fetch the decision from Cache
        res2 = self.resolver.resolve(
            question="Show sales for the past 5 years",
            capability=capability,
            connection_id=conn_id,
            reference_date=self.ref_date
        )
        self.assertTrue(res2.resolved)
        self.assertEqual(res2.plan.strategy, TimeStrategyType.SNAPSHOT)
        self.assertEqual(res2.selection_reason, StrategySelectionReason.CACHED)

    def test_invalid_unknown_query_path(self):
        # Scenario: Raw text contains no temporal expression
        result = self.resolver.resolve(
            question="List all products",
            reference_date=self.ref_date
        )
        self.assertFalse(result.resolved)
        self.assertIsNone(result.intent)
        self.assertIn("Could not detect any temporal intent", result.warnings[0])


if __name__ == "__main__":
    unittest.main()
