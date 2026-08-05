import unittest
import datetime
from semantic.temporal.enums import TimeStrategyType, CalendarType, TimeIntentType, StrategySelectionReason
from semantic.temporal.models import TimeSettings, LastNYearsIntent, FiscalYTDIntent, LastNDaysIntent, StrategyCandidate
from semantic.temporal.strategy_priorities import StrategyPriorityEngine, DEFAULT_PRIORITIES


class TestStrategyPriorities(unittest.TestCase):

    def setUp(self):
        self.priority_engine = StrategyPriorityEngine()
        self.ref_date = datetime.date(2026, 8, 5)

    def test_default_priorities_lookup(self):
        self.assertEqual(self.priority_engine.get_priority(TimeStrategyType.SNAPSHOT), 100)
        self.assertEqual(self.priority_engine.get_priority(TimeStrategyType.FISCAL), 95)
        self.assertEqual(self.priority_engine.get_priority(TimeStrategyType.CALENDAR_DIMENSION), 85)
        self.assertEqual(self.priority_engine.get_priority(TimeStrategyType.DATE_COLUMN), 70)
        self.assertEqual(self.priority_engine.get_priority(TimeStrategyType.DERIVED), 50)

    def test_admin_priority_overrides(self):
        custom_priorities = {
            TimeStrategyType.CALENDAR_DIMENSION: 110,
            TimeStrategyType.SNAPSHOT: 90
        }
        engine = StrategyPriorityEngine(priorities=custom_priorities)
        self.assertEqual(engine.get_priority(TimeStrategyType.CALENDAR_DIMENSION), 110)
        self.assertEqual(engine.get_priority(TimeStrategyType.SNAPSHOT), 90)
        self.assertEqual(engine.get_priority(TimeStrategyType.DATE_COLUMN), 0)  # Not in dict

    def test_contextual_rules_partial_snapshot(self):
        candidate = StrategyCandidate(
            strategy=TimeStrategyType.SNAPSHOT,
            reason=StrategySelectionReason.SNAPSHOT_PARTIAL
        )
        intent = LastNYearsIntent(count=5, reference_date=self.ref_date)
        settings = TimeSettings()
        
        score = self.priority_engine.evaluate(candidate, intent, settings)
        self.assertEqual(score, 60)  # Clamping/partial snapshot penalty

    def test_contextual_rules_fiscal_default_boost(self):
        candidate = StrategyCandidate(
            strategy=TimeStrategyType.FISCAL,
            reason=StrategySelectionReason.FINANCIAL_YEAR
        )
        intent = FiscalYTDIntent(reference_date=self.ref_date)
        
        # Scenario A: Fiscal calendar is default -> Boosted to 100
        settings_fiscal = TimeSettings(default_calendar=CalendarType.FISCAL)
        score_a = self.priority_engine.evaluate(candidate, intent, settings_fiscal)
        self.assertEqual(score_a, 100)
        
        # Scenario B: Standard calendar is default -> 90
        settings_calendar = TimeSettings(default_calendar=CalendarType.CALENDAR)
        score_b = self.priority_engine.evaluate(candidate, intent, settings_calendar)
        self.assertEqual(score_b, 90)

    def test_contextual_rules_date_column_granularity_boost(self):
        candidate = StrategyCandidate(
            strategy=TimeStrategyType.DATE_COLUMN,
            reason=StrategySelectionReason.DATE_COLUMNS
        )
        # Daily intent -> Boosted to 95
        intent_d = LastNDaysIntent(count=30, reference_date=self.ref_date)
        settings = TimeSettings()
        
        score = self.priority_engine.evaluate(candidate, intent_d, settings)
        self.assertEqual(score, 95)


if __name__ == "__main__":
    unittest.main()
