import datetime
import unittest
import os
import sys

# Adjust Python path to resolve packages correctly from the backend directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.temporal import (
    TimeSettings,
    DateCalculator,
    Granularity,
    LastNYearsIntent,
    LastNMonthsIntent,
    LastNDaysIntent,
    PreviousMonthIntent,
    CurrentMonthIntent,
    PreviousYearIntent,
    CurrentYearIntent,
    DateRangeIntent,
    YearRangeIntent,
    MonthRangeIntent,
    FiscalYTDIntent,
    YTDIntent,
    MTDIntent,
    QTDIntent,
    CalendarType,
)


class TestDateCalculator(unittest.TestCase):
    def setUp(self):
        self.ref_date = datetime.date(2026, 8, 4)
        self.default_settings = TimeSettings()
        self.calculator = DateCalculator(self.default_settings)

    def test_last_n_years(self):
        intent = LastNYearsIntent(count=5, reference_date=self.ref_date)
        res = self.calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2022, 1, 1))
        self.assertEqual(res.end_date, datetime.date(2026, 12, 31))
        self.assertEqual(res.granularity, Granularity.YEAR)

    def test_last_n_months(self):
        intent = LastNMonthsIntent(count=6, reference_date=self.ref_date)
        res = self.calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2026, 2, 4))
        self.assertEqual(res.end_date, self.ref_date)
        self.assertEqual(res.granularity, Granularity.MONTH)

    def test_previous_month(self):
        intent = PreviousMonthIntent(reference_date=self.ref_date)
        res = self.calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2026, 7, 1))
        self.assertEqual(res.end_date, datetime.date(2026, 7, 31))
        self.assertEqual(res.granularity, Granularity.MONTH)

    def test_current_month(self):
        intent = CurrentMonthIntent(reference_date=self.ref_date)
        res = self.calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2026, 8, 1))
        self.assertEqual(res.end_date, datetime.date(2026, 8, 31))
        self.assertEqual(res.granularity, Granularity.MONTH)

    def test_previous_year(self):
        intent = PreviousYearIntent(reference_date=self.ref_date)
        res = self.calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2025, 1, 1))
        self.assertEqual(res.end_date, datetime.date(2025, 12, 31))
        self.assertEqual(res.granularity, Granularity.YEAR)

    def test_current_year(self):
        intent = CurrentYearIntent(reference_date=self.ref_date)
        res = self.calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2026, 1, 1))
        self.assertEqual(res.end_date, datetime.date(2026, 12, 31))
        self.assertEqual(res.granularity, Granularity.YEAR)

    def test_date_range(self):
        start = datetime.date(2025, 5, 10)
        end = datetime.date(2025, 6, 20)
        intent = DateRangeIntent(start_date=start, end_date=end, reference_date=self.ref_date)
        res = self.calculator.calculate(intent)
        self.assertEqual(res.start_date, start)
        self.assertEqual(res.end_date, end)
        self.assertEqual(res.granularity, Granularity.DAY)

    def test_year_range(self):
        intent = YearRangeIntent(start_year=2021, end_year=2023, reference_date=self.ref_date)
        res = self.calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2021, 1, 1))
        self.assertEqual(res.end_date, datetime.date(2023, 12, 31))
        self.assertEqual(res.granularity, Granularity.YEAR)

    def test_month_range(self):
        intent = MonthRangeIntent(start_year=2025, start_month=3, end_year=2025, end_month=8, reference_date=self.ref_date)
        res = self.calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2025, 3, 1))
        self.assertEqual(res.end_date, datetime.date(2025, 8, 31))
        self.assertEqual(res.granularity, Granularity.MONTH)

    def test_fiscal_ytd_april(self):
        settings = TimeSettings(financial_year_start_month=4)
        calculator = DateCalculator(settings)
        intent = FiscalYTDIntent(reference_date=self.ref_date)
        res = calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2026, 4, 1))
        self.assertEqual(res.end_date, self.ref_date)

    def test_fiscal_ytd_july(self):
        settings = TimeSettings(financial_year_start_month=7)
        calculator = DateCalculator(settings)
        intent = FiscalYTDIntent(reference_date=self.ref_date)
        res = calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2026, 7, 1))
        self.assertEqual(res.end_date, self.ref_date)

    def test_ytd(self):
        intent = YTDIntent(reference_date=self.ref_date)
        res = self.calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2026, 1, 1))
        self.assertEqual(res.end_date, self.ref_date)

    def test_mtd(self):
        intent = MTDIntent(reference_date=self.ref_date)
        res = self.calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2026, 8, 1))
        self.assertEqual(res.end_date, self.ref_date)
        self.assertEqual(res.granularity, Granularity.MONTH)

    def test_qtd(self):
        intent = QTDIntent(reference_date=self.ref_date)
        res = self.calculator.calculate(intent)
        self.assertEqual(res.start_date, datetime.date(2026, 7, 1))
        self.assertEqual(res.end_date, self.ref_date)
        self.assertEqual(res.granularity, Granularity.QUARTER)


if __name__ == "__main__":
    unittest.main()
