import unittest
import datetime
from semantic.temporal.models import (
    TimeCapability,
    TimeSettings,
    TimeResolutionResult,
    ResolvedTimePlan,
    LastNYearsIntent,
    FiscalYTDIntent,
)
from semantic.temporal.enums import (
    TimeStrategyType,
    CalendarType,
    Granularity,
    StrategySelectionReason,
)
from semantic.temporal.exceptions import ContextBuildException
from semantic.temporal.context_builder import TimeContextBuilder


class TestTimeContextBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = TimeContextBuilder()
        self.ref_date = datetime.date(2026, 8, 5)

    def test_snapshot_scenario(self):
        intent = LastNYearsIntent(count=5, reference_date=self.ref_date)
        plan = ResolvedTimePlan(
            strategy=TimeStrategyType.SNAPSHOT,
            snapshot_columns=["CY", "PY", "PPY", "PPPY", "PPPPY"],
            grouping=Granularity.YEAR,
            warnings=["Using snapshot columns fallback"]
        )
        resolution = TimeResolutionResult(
            resolved=True,
            intent=intent,
            plan=plan,
            is_partial=False,
            warnings=["Using snapshot columns fallback"]
        )
        settings = TimeSettings()

        context = self.builder.build(resolution, settings)
        self.assertEqual(context.strategy, TimeStrategyType.SNAPSHOT)
        self.assertEqual(context.snapshot_columns, ["CY", "PY", "PPY", "PPPY", "PPPPY"])
        self.assertEqual(context.warnings, ["Using snapshot columns fallback"])
        self.assertEqual(context.grouping, Granularity.YEAR)
        self.assertEqual(context.intent, intent)

    def test_date_column_scenario(self):
        intent = LastNYearsIntent(count=3, reference_date=self.ref_date)
        plan = ResolvedTimePlan(
            strategy=TimeStrategyType.DATE_COLUMN,
            date_column="OrderDate",
            start_date=datetime.date(2023, 1, 1),
            end_date=datetime.date(2025, 12, 31),
        )
        resolution = TimeResolutionResult(
            resolved=True,
            intent=intent,
            plan=plan
        )
        settings = TimeSettings()

        context = self.builder.build(resolution, settings)
        self.assertEqual(context.strategy, TimeStrategyType.DATE_COLUMN)
        self.assertEqual(context.date_column, "OrderDate")
        self.assertEqual(context.start_date, datetime.date(2023, 1, 1))
        self.assertEqual(context.end_date, datetime.date(2025, 12, 31))

    def test_calendar_dimension_scenario(self):
        intent = LastNYearsIntent(count=3, reference_date=self.ref_date)
        plan = ResolvedTimePlan(
            strategy=TimeStrategyType.CALENDAR_DIMENSION,
            calendar_table="DimDate",
            start_date=datetime.date(2023, 1, 1),
            end_date=datetime.date(2025, 12, 31),
        )
        resolution = TimeResolutionResult(
            resolved=True,
            intent=intent,
            plan=plan
        )
        settings = TimeSettings(default_calendar=CalendarType.CALENDAR)

        context = self.builder.build(resolution, settings)
        self.assertEqual(context.strategy, TimeStrategyType.CALENDAR_DIMENSION)
        self.assertEqual(context.calendar_table, "DimDate")
        self.assertEqual(context.calendar_type, CalendarType.CALENDAR)

    def test_financial_year_scenario(self):
        intent = FiscalYTDIntent(reference_date=self.ref_date)
        plan = ResolvedTimePlan(
            strategy=TimeStrategyType.FISCAL,
            start_date=datetime.date(2026, 4, 1),
            end_date=self.ref_date,
        )
        resolution = TimeResolutionResult(
            resolved=True,
            intent=intent,
            plan=plan
        )
        settings = TimeSettings(
            default_calendar=CalendarType.FISCAL,
            financial_year_start_month=4,
            timezone="Asia/Kolkata",
            locale="en_IN"
        )

        context = self.builder.build(resolution, settings)
        self.assertEqual(context.financial_year_start_month, 4)
        self.assertEqual(context.calendar_type, CalendarType.FISCAL)
        self.assertEqual(context.timezone, "Asia/Kolkata")
        self.assertEqual(context.locale, "en_IN")

    def test_partial_history_scenario(self):
        intent = LastNYearsIntent(count=5, reference_date=self.ref_date)
        plan = ResolvedTimePlan(
            strategy=TimeStrategyType.SNAPSHOT,
            snapshot_columns=["CY", "PY"],
            warnings=["only 2 years are available"]
        )
        resolution = TimeResolutionResult(
            resolved=True,
            intent=intent,
            plan=plan,
            is_partial=True,
            warnings=["only 2 years are available"]
        )
        settings = TimeSettings()

        context = self.builder.build(resolution, settings)
        self.assertTrue(context.is_partial)
        self.assertEqual(context.warnings, ["only 2 years are available"])

    def test_failed_resolution_raises_exception(self):
        resolution = TimeResolutionResult(
            resolved=False,
            warnings=["Detection failed"]
        )
        settings = TimeSettings()

        with self.assertRaises(ContextBuildException) as exc:
            self.builder.build(resolution, settings)

        self.assertIn("temporal resolution failed", str(exc.exception))

    def test_context_immutability(self):
        intent = LastNYearsIntent(count=3, reference_date=self.ref_date)
        plan = ResolvedTimePlan(
            strategy=TimeStrategyType.DATE_COLUMN,
            date_column="OrderDate",
        )
        resolution = TimeResolutionResult(
            resolved=True,
            intent=intent,
            plan=plan
        )
        settings = TimeSettings()
        context = self.builder.build(resolution, settings)
        
        # Expect dataclasses.FrozenInstanceError upon trying to mutate a field
        from dataclasses import FrozenInstanceError
        with self.assertRaises(FrozenInstanceError):
            context.date_column = "NewColumn"


if __name__ == "__main__":
    unittest.main()
