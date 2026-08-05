import unittest
import datetime
from semantic.temporal.models import TimeCapability, TimeSettings
from semantic.temporal.enums import TimeStrategyType, StrategySelectionReason
from semantic.temporal.strategy_candidate_generator import StrategyCandidateGenerator
from semantic.temporal.models import (
    LastNYearsIntent,
    LastNDaysIntent,
    FiscalYTDIntent,
)


class TestCandidateGenerator(unittest.TestCase):

    def setUp(self):
        self.generator = StrategyCandidateGenerator()
        self.ref_date = datetime.date(2026, 8, 5)
        self.settings = TimeSettings()

    def test_past_5_years_candidates(self):
        intent = LastNYearsIntent(count=5, reference_date=self.ref_date)
        capability = TimeCapability(
            date_columns=["OrderDate"],
            snapshot_mapping={0: "CY", 1: "PY"}
        )
        
        candidates = self.generator.generate(intent, capability, self.settings)
        strategies = [c.strategy for c in candidates]
        
        self.assertIn(TimeStrategyType.SNAPSHOT, strategies)
        self.assertIn(TimeStrategyType.DATE_COLUMN, strategies)
        
        # Verify that snapshot candidate has SNAPSHOT_PARTIAL reason
        snap_cand = next(c for c in candidates if c.strategy == TimeStrategyType.SNAPSHOT)
        self.assertEqual(snap_cand.reason, StrategySelectionReason.SNAPSHOT_PARTIAL)

    def test_fiscal_ytd_candidates(self):
        intent = FiscalYTDIntent(reference_date=self.ref_date)
        capability = TimeCapability(
            date_columns=["OrderDate"],
            supports_time_hierarchy=True  # triggers supports_fiscal_calendar property
        )
        
        candidates = self.generator.generate(intent, capability, self.settings)
        strategies = [c.strategy for c in candidates]
        
        self.assertIn(TimeStrategyType.FISCAL, strategies)
        self.assertIn(TimeStrategyType.DATE_COLUMN, strategies)
        
        fiscal_cand = next(c for c in candidates if c.strategy == TimeStrategyType.FISCAL)
        self.assertEqual(fiscal_cand.reason, StrategySelectionReason.FINANCIAL_YEAR)

    def test_date_only_candidates(self):
        intent = LastNDaysIntent(count=30, reference_date=self.ref_date)
        capability = TimeCapability(
            date_columns=["OrderDate"]
        )
        
        candidates = self.generator.generate(intent, capability, self.settings)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].strategy, TimeStrategyType.DATE_COLUMN)
        self.assertEqual(candidates[0].reason, StrategySelectionReason.DATE_COLUMNS)


if __name__ == "__main__":
    unittest.main()
