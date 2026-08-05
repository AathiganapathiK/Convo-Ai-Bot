import unittest
import datetime
from semantic.temporal.models import TimeCapability, TimeSettings, YearRange, StrategyCandidate
from semantic.temporal.enums import TimeStrategyType, CalendarType, TimeIntentType, StrategySelectionReason
from semantic.temporal.strategy_selector import TimeStrategySelector, StrategySelectionResult
from semantic.temporal.capability_cache import TimeResolutionCache
from semantic.temporal.models import (
    LastNYearsIntent,
    LastNDaysIntent,
    FiscalYTDIntent,
    DateRangeIntent,
)


class TestStrategySelector(unittest.TestCase):

    def setUp(self):
        self.selector = TimeStrategySelector()
        self.ref_date = datetime.date(2026, 8, 5)
        TimeResolutionCache.clear()

    def tearDown(self):
        TimeResolutionCache.clear()

    def test_past_5_years_snapshot_plus_date(self):
        # Scenario: Past 5 years sales with Snapshot + Date columns available
        # Expect: Snapshot strategy (high score due to direct year match)
        intent = LastNYearsIntent(count=5, reference_date=self.ref_date)
        capability = TimeCapability(
            date_columns=["OrderDate"],
            snapshot_mapping={0: "CY", 1: "PY", 2: "PPY", 3: "PPPY", 4: "PPPPY"}
        )
        settings = TimeSettings()
        
        result = self.selector.select(intent, capability, settings)
        self.assertEqual(result.strategy, TimeStrategyType.SNAPSHOT)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.reason, StrategySelectionReason.SNAPSHOT_COLUMNS)

    def test_daily_sales_snapshot_plus_date(self):
        # Scenario: Daily sales trend with Snapshot + Date columns available
        # Expect: Date Column strategy (as daily granularity does not fit snapshot)
        intent = LastNDaysIntent(count=30, reference_date=self.ref_date)
        capability = TimeCapability(
            date_columns=["OrderDate"],
            snapshot_mapping={0: "CY", 1: "PY"}
        )
        settings = TimeSettings()
        
        result = self.selector.select(intent, capability, settings)
        self.assertEqual(result.strategy, TimeStrategyType.DATE_COLUMN)
        self.assertEqual(result.score, 95)
        self.assertEqual(result.reason, StrategySelectionReason.DATE_COLUMNS)

    def test_financial_ytd_fiscal_plus_date(self):
        # Scenario: Financial YTD with Fiscal calendar support + Date columns
        # Expect: Fiscal strategy
        intent = FiscalYTDIntent(reference_date=self.ref_date)
        capability = TimeCapability(
            date_columns=["OrderDate"]
        )
        settings = TimeSettings(default_calendar=CalendarType.FISCAL)
        
        result = self.selector.select(intent, capability, settings)
        self.assertEqual(result.strategy, TimeStrategyType.FISCAL)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.reason, StrategySelectionReason.FINANCIAL_YEAR)

    def test_sales_in_2022_calendar_plus_date(self):
        # Scenario: Year range query "Sales in 2022" with Calendar Dimension + Date columns
        # Expect: Calendar Dimension
        intent = DateRangeIntent(
            start_date=datetime.date(2022, 1, 1),
            end_date=datetime.date(2022, 12, 31),
            reference_date=self.ref_date
        )
        capability = TimeCapability(
            date_columns=["OrderDate"],
            calendar_tables=["DimCalendar"]
        )
        settings = TimeSettings()
        
        result = self.selector.select(intent, capability, settings)
        self.assertEqual(result.strategy, TimeStrategyType.CALENDAR_DIMENSION)
        self.assertEqual(result.score, 85)
        self.assertEqual(result.reason, StrategySelectionReason.CALENDAR_TABLE)

    def test_last_30_days_date_only(self):
        # Scenario: Last 30 days query with only Date column available
        # Expect: Date Column
        intent = LastNDaysIntent(count=30, reference_date=self.ref_date)
        capability = TimeCapability(
            date_columns=["OrderDate"]
        )
        settings = TimeSettings()
        
        result = self.selector.select(intent, capability, settings)
        self.assertEqual(result.strategy, TimeStrategyType.DATE_COLUMN)
        self.assertEqual(result.reason, StrategySelectionReason.DATE_COLUMNS)

    def test_snapshot_unavailable_calendar(self):
        # Scenario: Yearly query, Snapshot is not available, but Calendar is available
        # Expect: Calendar Dimension
        intent = LastNYearsIntent(count=5, reference_date=self.ref_date)
        capability = TimeCapability(
            calendar_tables=["DimCalendar"],
            date_columns=["OrderDate"]
        )
        settings = TimeSettings()
        
        result = self.selector.select(intent, capability, settings)
        self.assertEqual(result.strategy, TimeStrategyType.CALENDAR_DIMENSION)
        self.assertEqual(result.reason, StrategySelectionReason.CALENDAR_TABLE)

    def test_cache_strategy_selections(self):
        # Scenario: Verifying caching of selections per intent type
        intent_y = LastNYearsIntent(count=5, reference_date=self.ref_date)
        intent_d = LastNDaysIntent(count=30, reference_date=self.ref_date)
        
        capability = TimeCapability(
            date_columns=["OrderDate"],
            snapshot_mapping={0: "CY", 1: "PY", 2: "PPY", 3: "PPPY", 4: "PPPPY"}
        )
        settings = TimeSettings()
        conn_id = "selector_conn_id"
        
        # Select for yearly intent -> Caches SNAPSHOT
        res_y = self.selector.select(intent_y, capability, settings, connection_id=conn_id)
        self.assertEqual(res_y.strategy, TimeStrategyType.SNAPSHOT)
        
        # Select for daily intent -> Caches DATE_COLUMN
        res_d = self.selector.select(intent_d, capability, settings, connection_id=conn_id)
        self.assertEqual(res_d.strategy, TimeStrategyType.DATE_COLUMN)
        
        # Retrieve and verify cached entries
        cached_entry = TimeResolutionCache.get(conn_id)
        self.assertIsNotNone(cached_entry)
        self.assertEqual(cached_entry.strategy_selections[TimeIntentType.LAST_N_YEARS], TimeStrategyType.SNAPSHOT)
        self.assertEqual(cached_entry.strategy_selections[TimeIntentType.LAST_N_DAYS], TimeStrategyType.DATE_COLUMN)


if __name__ == "__main__":
    unittest.main()
