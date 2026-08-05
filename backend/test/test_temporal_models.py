import datetime
import json
import os
import sys
import unittest
from dataclasses import asdict

# Adjust Python path to resolve packages correctly from the backend directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.temporal import (
    TimeIntentType,
    CalendarType,
    Granularity,
    TimeStrategyType,
    RelativeTimeDirection,
    LastNYearsIntent,
    DateRangeIntent,
    YearRangeIntent,
    MonthRangeIntent,
    YearComparisonIntent,
    MonthComparisonIntent,
    TimeResolutionResult,
    TimeCapability,
    ResolvedTimePlan,
    TimeIntentValidator,
    DetectedTimeExpression,
    YearRange,
    DateRange,
    TemporalDetector,
    TimeStrategyResolver,
    FiscalYTDIntent,
    TimeSettings,
)


class TestTemporalModels(unittest.TestCase):
    def test_enum_members(self):
        # Validate critical enums exist and hold expected values
        self.assertEqual(TimeIntentType.LAST_N_YEARS, "LAST_N_YEARS")
        self.assertEqual(CalendarType.FISCAL, "FISCAL")
        self.assertEqual(Granularity.MONTH, "MONTH")
        self.assertEqual(TimeStrategyType.DATE_COLUMN, "DATE_COLUMN")
        self.assertEqual(RelativeTimeDirection.ROLLING, "ROLLING")

    def test_model_instantiation(self):
        # Test LastNYearsIntent instantiation
        ref_date = datetime.date(2025, 1, 15)
        intent = LastNYearsIntent(count=3, reference_date=ref_date, calendar_type=CalendarType.CALENDAR)
        self.assertEqual(intent.count, 3)
        self.assertEqual(intent.reference_date, ref_date)
        self.assertEqual(intent.calendar_type, CalendarType.CALENDAR)
        self.assertEqual(intent.intent_type, TimeIntentType.LAST_N_YEARS)

        # Test TimeResolutionResult instantiation
        plan = ResolvedTimePlan(
            strategy=TimeStrategyType.DATE_COLUMN,
            start_date=datetime.date(2022, 1, 1),
            end_date=datetime.date(2024, 12, 31),
        )
        res = TimeResolutionResult(
            resolved=True,
            intent=intent,
            plan=plan,
            confidence=0.95,
        )
        self.assertTrue(res.resolved)
        self.assertEqual(res.confidence, 0.95)
        self.assertEqual(res.plan.start_date, datetime.date(2022, 1, 1))

        # Test TimeCapability
        cap = TimeCapability(
            date_columns=["OrderDate", "ShipDate"],
            supports_time_hierarchy=True,
            available_year_range=YearRange(min_year=2021, max_year=2023),
            available_date_range=DateRange(
                start_date=datetime.date(2021, 1, 1),
                end_date=datetime.date(2023, 12, 31),
            ),
        )
        self.assertTrue(cap.supports_date_columns)
        self.assertTrue(cap.supports_fiscal_calendar)
        self.assertTrue(cap.supports_time_hierarchy)
        self.assertIsNotNone(cap.available_year_range)
        self.assertEqual(cap.available_year_range.min_year, 2021)
        self.assertEqual(cap.available_year_range.max_year, 2023)
        self.assertIsNotNone(cap.available_date_range)
        self.assertEqual(cap.available_date_range.start_date, datetime.date(2021, 1, 1))
        self.assertEqual(cap.available_date_range.end_date, datetime.date(2023, 12, 31))

        # Test TimeSettings
        settings = TimeSettings(
            financial_year_start_month=4,
            timezone="Asia/Kolkata"
        )
        self.assertEqual(settings.financial_year_start_month, 4)
        self.assertEqual(settings.timezone, "Asia/Kolkata")

        # Test ResolvedTimePlan
        plan = ResolvedTimePlan(
            strategy=TimeStrategyType.DATE_COLUMN,
            date_column="OrderDate",
            grouping=Granularity.YEAR,
        )
        self.assertEqual(plan.strategy, TimeStrategyType.DATE_COLUMN)
        self.assertEqual(plan.date_column, "OrderDate")
        self.assertEqual(plan.grouping, Granularity.YEAR)

        # Test DetectedTimeExpression
        expr = DetectedTimeExpression(
            text="past five years",
            intent=TimeIntentType.LAST_N_YEARS,
            confidence=0.96,
            matched_tokens=["past", "five", "years"],
        )
        self.assertEqual(expr.text, "past five years")
        self.assertEqual(expr.intent, TimeIntentType.LAST_N_YEARS)
        self.assertEqual(expr.confidence, 0.96)
        self.assertEqual(expr.matched_tokens, ["past", "five", "years"])

    def test_validation_last_n(self):
        # Valid LastNYearsIntent
        intent_ok = LastNYearsIntent(count=5)
        res = TimeIntentValidator.validate(intent_ok)
        self.assertTrue(res.passed)
        self.assertEqual(len(res.errors), 0)

        # Invalid LastNYearsIntent (count <= 0)
        intent_bad = LastNYearsIntent(count=0)
        res_bad = TimeIntentValidator.validate(intent_bad)
        self.assertFalse(res_bad.passed)
        self.assertIn("Count must be greater than 0", res_bad.errors[0])

        intent_bad_negative = LastNYearsIntent(count=-2)
        res_bad_neg = TimeIntentValidator.validate(intent_bad_negative)
        self.assertFalse(res_bad_neg.passed)
        self.assertIn("Count must be greater than 0", res_bad_neg.errors[0])

    def test_validation_date_range(self):
        # Valid DateRangeIntent
        start = datetime.date(2025, 1, 1)
        end = datetime.date(2025, 12, 31)
        intent_ok = DateRangeIntent(start_date=start, end_date=end)
        res = TimeIntentValidator.validate(intent_ok)
        self.assertTrue(res.passed)

        # Invalid DateRangeIntent (start > end)
        intent_bad = DateRangeIntent(start_date=end, end_date=start)
        res_bad = TimeIntentValidator.validate(intent_bad)
        self.assertFalse(res_bad.passed)
        self.assertIn("cannot be after end date", res_bad.errors[0])

    def test_validation_year_range(self):
        # Valid YearRangeIntent
        intent_ok = YearRangeIntent(start_year=2020, end_year=2025)
        res = TimeIntentValidator.validate(intent_ok)
        self.assertTrue(res.passed)

        # Invalid YearRangeIntent
        intent_bad = YearRangeIntent(start_year=2025, end_year=2020)
        res_bad = TimeIntentValidator.validate(intent_bad)
        self.assertFalse(res_bad.passed)
        self.assertIn("cannot be after end year", res_bad.errors[0])

    def test_validation_month_range(self):
        # Valid MonthRangeIntent
        intent_ok = MonthRangeIntent(start_month=3, start_year=2022, end_month=8, end_year=2022)
        res = TimeIntentValidator.validate(intent_ok)
        self.assertTrue(res.passed)

        # Invalid MonthRangeIntent (start month > end month in same year)
        intent_bad = MonthRangeIntent(start_month=9, start_year=2022, end_month=3, end_year=2022)
        res_bad = TimeIntentValidator.validate(intent_bad)
        self.assertFalse(res_bad.passed)
        self.assertIn("cannot be after end month", res_bad.errors[0])

        # Invalid MonthRangeIntent (invalid month value)
        intent_bad_month = MonthRangeIntent(start_month=13, start_year=2022, end_month=5, end_year=2022)
        res_bad_month = TimeIntentValidator.validate(intent_bad_month)
        self.assertFalse(res_bad_month.passed)
        self.assertIn("Months must be between 1 and 12", res_bad_month.errors[0])

    def test_validation_year_comparison(self):
        # Valid YearComparisonIntent
        intent_ok = YearComparisonIntent(start_year=2019, end_year=2021)
        res = TimeIntentValidator.validate(intent_ok)
        self.assertTrue(res.passed)

        # Invalid YearComparisonIntent
        intent_bad = YearComparisonIntent(start_year=2022, end_year=2020)
        res_bad = TimeIntentValidator.validate(intent_bad)
        self.assertFalse(res_bad.passed)
        self.assertIn("cannot be after end year", res_bad.errors[0])

    def test_validation_month_comparison(self):
        # Valid MonthComparisonIntent
        intent_ok = MonthComparisonIntent(start_month=1, start_year=2020, end_month=12, end_year=2020)
        res = TimeIntentValidator.validate(intent_ok)
        self.assertTrue(res.passed)

        # Invalid MonthComparisonIntent
        intent_bad = MonthComparisonIntent(start_month=12, start_year=2020, end_month=1, end_year=2020)
        res_bad = TimeIntentValidator.validate(intent_bad)
        self.assertFalse(res_bad.passed)
        self.assertIn("cannot be after end month", res_bad.errors[0])

    def test_serialization(self):
        # Test serialization of intents to dictionaries
        intent = LastNYearsIntent(count=2, reference_date=datetime.date(2025, 6, 1))
        serialized = asdict(intent)
        self.assertEqual(serialized["count"], 2)
        self.assertEqual(serialized["calendar_type"], CalendarType.AUTO)
        self.assertEqual(serialized["intent_type"], TimeIntentType.LAST_N_YEARS)

    def test_golden_dataset_exists(self):
        # Verify that golden dataset JSON is correctly written and formatted
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "time_intent_cases.json"))
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as f:
            cases = json.load(f)
        self.assertIsInstance(cases, list)
        self.assertGreater(len(cases), 0)
        self.assertEqual(cases[0]["question"], "past five years sales")
        self.assertEqual(cases[0]["intent"], "LAST_N_YEARS")
        self.assertEqual(cases[0]["count"], 5)

    def test_detector_golden_dataset(self):
        detector = TemporalDetector()
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "time_intent_cases.json"))
        with open(path, "r", encoding="utf-8") as f:
            cases = json.load(f)

        ref_date = datetime.date(2026, 8, 4)
        for i, case in enumerate(cases):
            question = case["question"]
            expected_intent = case["intent"]
            
            with self.subTest(i=i, question=question):
                intent = detector.detect(question, reference_date=ref_date)
                self.assertIsNotNone(
                    intent,
                    f"Failed to detect temporal intent for: '{question}'"
                )
                self.assertEqual(
                    intent.intent_type, expected_intent,
                    f"Incorrect intent type for '{question}': expected {expected_intent}, got {intent.intent_type}"
                )
                
                # Verify specific attributes
                if "count" in case:
                    self.assertEqual(
                        getattr(intent, "count"), case["count"],
                        f"Incorrect count for '{question}': expected {case['count']}, got {getattr(intent, 'count')}"
                    )
                if "start_year" in case:
                    self.assertEqual(
                        getattr(intent, "start_year"), case["start_year"],
                        f"Incorrect start_year for '{question}': expected {case['start_year']}, got {getattr(intent, 'start_year')}"
                    )
                if "end_year" in case:
                    self.assertEqual(
                        getattr(intent, "end_year"), case["end_year"],
                        f"Incorrect end_year for '{question}': expected {case['end_year']}, got {getattr(intent, 'end_year')}"
                    )
                if "start_month" in case:
                    self.assertEqual(
                        getattr(intent, "start_month"), case["start_month"],
                        f"Incorrect start_month for '{question}': expected {case['start_month']}, got {getattr(intent, 'start_month')}"
                    )
                if "end_month" in case:
                    self.assertEqual(
                        getattr(intent, "end_month"), case["end_month"],
                        f"Incorrect end_month for '{question}': expected {case['end_month']}, got {getattr(intent, 'end_month')}"
                    )

    def test_strategy_resolver(self):
        resolver = TimeStrategyResolver()
        ref_date = datetime.date(2026, 8, 4)
        
        # 1. Test Snapshot Strategy
        intent_last_5 = LastNYearsIntent(count=5, reference_date=ref_date)
        cap_snapshot = TimeCapability(
            snapshot_mapping={0: "CY", 1: "PY", 2: "PPY", 3: "PPPY", 4: "PPPPY"}
        )
        plan_snapshot = resolver.resolve(intent_last_5, cap_snapshot)
        self.assertEqual(plan_snapshot.strategy, TimeStrategyType.SNAPSHOT)
        self.assertEqual(plan_snapshot.snapshot_columns, ["CY", "PY", "PPY", "PPPY", "PPPPY"])
        
        # Test Snapshot Strategy for a different naming scheme
        intent_last_3 = LastNYearsIntent(count=3, reference_date=ref_date)
        cap_other_company = TimeCapability(
            snapshot_mapping={0: "TY", 1: "LY", 2: "LLY"}
        )
        plan_other = resolver.resolve(intent_last_3, cap_other_company)
        self.assertEqual(plan_other.strategy, TimeStrategyType.SNAPSHOT)
        self.assertEqual(plan_other.snapshot_columns, ["TY", "LY", "LLY"])
        
        # 2. Test Date Column Strategy
        cap_date = TimeCapability(
            date_columns=["OrderDate"],
            default_date_column="OrderDate"
        )
        plan_date = resolver.resolve(intent_last_5, cap_date)
        self.assertEqual(plan_date.strategy, TimeStrategyType.DATE_COLUMN)
        self.assertEqual(plan_date.date_column, "OrderDate")
        self.assertEqual(plan_date.start_date, datetime.date(2022, 1, 1))
        self.assertEqual(plan_date.end_date, datetime.date(2026, 12, 31))
        
        # 3. Test Calendar Dimension Strategy
        cap_calendar = TimeCapability(
            date_columns=["OrderDate"],
            calendar_tables=["DimCalendar"]
        )
        plan_calendar = resolver.resolve(intent_last_5, cap_calendar)
        self.assertEqual(plan_calendar.strategy, TimeStrategyType.CALENDAR_DIMENSION)
        self.assertEqual(plan_calendar.date_column, "OrderDate")
        self.assertEqual(plan_calendar.calendar_table, "DimCalendar")
        self.assertEqual(plan_calendar.start_date, datetime.date(2022, 1, 1))
        self.assertEqual(plan_calendar.end_date, datetime.date(2026, 12, 31))
        
        # 4. Test Configurable Financial Year
        # Reference date: 2026-08-04
        intent_fiscal = FiscalYTDIntent(reference_date=ref_date)
        cap_fiscal = TimeCapability(
            date_columns=["OrderDate"]
        )
        
        # Test financial_year_start_month=4 (April -> March, Ramraj)
        settings_4 = TimeSettings(financial_year_start_month=4)
        plan_fiscal_4 = resolver.resolve(intent_fiscal, cap_fiscal, settings_4)
        self.assertEqual(plan_fiscal_4.strategy, TimeStrategyType.FISCAL)
        self.assertEqual(plan_fiscal_4.start_date, datetime.date(2026, 4, 1))
        self.assertEqual(plan_fiscal_4.end_date, datetime.date(2026, 8, 4))
        
        # Test financial_year_start_month=7 (July -> June)
        settings_7 = TimeSettings(financial_year_start_month=7)
        plan_fiscal_7 = resolver.resolve(intent_fiscal, cap_fiscal, settings_7)
        self.assertEqual(plan_fiscal_7.strategy, TimeStrategyType.FISCAL)
        self.assertEqual(plan_fiscal_7.start_date, datetime.date(2026, 7, 1))
        self.assertEqual(plan_fiscal_7.end_date, datetime.date(2026, 8, 4))
        
        # Test financial_year_start_month=1 (January -> December)
        settings_1 = TimeSettings(financial_year_start_month=1)
        plan_fiscal_1 = resolver.resolve(intent_fiscal, cap_fiscal, settings_1)
        self.assertEqual(plan_fiscal_1.strategy, TimeStrategyType.FISCAL)
        self.assertEqual(plan_fiscal_1.start_date, datetime.date(2026, 1, 1))
        self.assertEqual(plan_fiscal_1.end_date, datetime.date(2026, 8, 4))

    def test_graceful_degradation(self):
        resolver = TimeStrategyResolver()
        ref_date = datetime.date(2026, 8, 4)
        
        # Test 1: Snapshot Capability 2024->2025, Question: Past 5 years
        intent_last_5 = LastNYearsIntent(count=5, reference_date=ref_date)
        cap_snap_degrad = TimeCapability(
            snapshot_mapping={0: "CY", 1: "PY"},
            available_year_range=YearRange(min_year=2024, max_year=2025)
        )
        plan_snap = resolver.resolve(intent_last_5, cap_snap_degrad)
        self.assertEqual(plan_snap.strategy, TimeStrategyType.SNAPSHOT)
        self.assertEqual(plan_snap.snapshot_columns, ["CY", "PY"])
        self.assertTrue(plan_snap.is_partial)
        self.assertEqual(plan_snap.requested_years, 5)
        self.assertEqual(plan_snap.available_years, 2)
        self.assertTrue(any("Requested 5 years, but only 2 years are available." in w for w in plan_snap.warnings))
        
        # Test 2: Date strategy available 2022-2025, Ask: Last 10 years
        intent_last_10 = LastNYearsIntent(count=10, reference_date=ref_date)
        cap_date = TimeCapability(
            date_columns=["OrderDate"],
            available_year_range=YearRange(min_year=2022, max_year=2025)
        )
        plan_date = resolver.resolve(intent_last_10, cap_date)
        self.assertEqual(plan_date.strategy, TimeStrategyType.DATE_COLUMN)
        self.assertEqual(plan_date.start_date, datetime.date(2022, 1, 1))
        self.assertTrue(plan_date.is_partial)
        self.assertEqual(plan_date.requested_years, 10)
        self.assertEqual(plan_date.available_years, 4)
        
        # Test 3: No degradation available 2019-2026, Ask: Last 3 years
        intent_last_3 = LastNYearsIntent(count=3, reference_date=ref_date)
        cap_no_degrad = TimeCapability(
            date_columns=["OrderDate"],
            available_year_range=YearRange(min_year=2019, max_year=2026)
        )
        plan_no_degrad = resolver.resolve(intent_last_3, cap_no_degrad)
        self.assertEqual(plan_no_degrad.strategy, TimeStrategyType.DATE_COLUMN)
        self.assertFalse(plan_no_degrad.is_partial)
        self.assertEqual(len(plan_no_degrad.warnings), 0)
        
        # Test 4: Snapshot mapping Capability {0: 'TY', 1: 'LY'}, Ask: Past 5 years
        cap_snap_other = TimeCapability(
            snapshot_mapping={0: "TY", 1: "LY"}
        )
        plan_snap_other = resolver.resolve(intent_last_5, cap_snap_other)
        self.assertEqual(plan_snap_other.strategy, TimeStrategyType.SNAPSHOT)
        self.assertEqual(plan_snap_other.snapshot_columns, ["TY", "LY"])
        self.assertTrue(plan_snap_other.is_partial)
        
        # Test 5: Calendar strategy, Available: 2023-2025, Ask: Last 10 years
        cap_calendar = TimeCapability(
            date_columns=["OrderDate"],
            calendar_tables=["DimCalendar"],
            available_year_range=YearRange(min_year=2023, max_year=2025)
        )
        plan_calendar = resolver.resolve(intent_last_10, cap_calendar)
        self.assertEqual(plan_calendar.strategy, TimeStrategyType.CALENDAR_DIMENSION)
        self.assertEqual(plan_calendar.start_date, datetime.date(2023, 1, 1))
        self.assertTrue(plan_calendar.is_partial)
        self.assertEqual(plan_calendar.requested_years, 10)
        self.assertEqual(plan_calendar.available_years, 3)


if __name__ == "__main__":
    unittest.main()
