import unittest
import datetime
from semantic.temporal.models import TimeContext, LastNYearsIntent
from semantic.temporal.enums import TimeStrategyType, CalendarType, Granularity
from semantic.temporal.temporal_prompt_formatter import TemporalPromptFormatter


class TestTemporalPromptFormatter(unittest.TestCase):

    def setUp(self):
        self.formatter = TemporalPromptFormatter()
        self.ref_date = datetime.date(2026, 8, 5)
        self.intent = LastNYearsIntent(count=3, reference_date=self.ref_date)

    def test_format_snapshot_strategy(self):
        context = TimeContext(
            intent=self.intent,
            strategy=TimeStrategyType.SNAPSHOT,
            snapshot_columns=["CY", "PY", "PPY"],
            grouping=Granularity.YEAR,
            calendar_type=CalendarType.CALENDAR,
            financial_year_start_month=1,
            timezone="UTC",
            locale="en_US"
        )
        formatted = self.formatter.format(context)
        self.assertIn("Temporal Context:", formatted)
        self.assertIn("Intent: LastNYearsIntent", formatted)
        self.assertIn("Strategy: SNAPSHOT", formatted)
        self.assertIn("Snapshot Columns: CY, PY, PPY", formatted)
        self.assertIn("Grouping: YEAR", formatted)
        self.assertIn("Calendar Type: CALENDAR", formatted)
        self.assertIn("Timezone: UTC", formatted)
        self.assertIn("Locale: en_US", formatted)

    def test_format_date_column_strategy(self):
        context = TimeContext(
            intent=self.intent,
            strategy=TimeStrategyType.DATE_COLUMN,
            date_column="OrderDate",
            start_date=datetime.date(2023, 1, 1),
            end_date=datetime.date(2025, 12, 31),
            grouping=Granularity.DAY,
            calendar_type=CalendarType.CALENDAR,
            timezone="America/New_York",
            locale="en_US"
        )
        formatted = self.formatter.format(context)
        self.assertIn("Strategy: DATE_COLUMN", formatted)
        self.assertIn("Date Column: OrderDate", formatted)
        self.assertIn("Start Date: 2023-01-01", formatted)
        self.assertIn("End Date: 2025-12-31", formatted)
        self.assertIn("Grouping: DAY", formatted)
        self.assertIn("Timezone: America/New_York", formatted)

    def test_format_partial_warning(self):
        context = TimeContext(
            intent=self.intent,
            strategy=TimeStrategyType.SNAPSHOT,
            snapshot_columns=["CY", "PY"],
            grouping=Granularity.YEAR,
            calendar_type=CalendarType.CALENDAR,
            is_partial=True,
            warnings=["only 2 years available"]
        )
        formatted = self.formatter.format(context)
        self.assertIn("Warning: Requested period exceeds available data.", formatted)
        self.assertIn("- only 2 years available", formatted)


if __name__ == "__main__":
    unittest.main()
