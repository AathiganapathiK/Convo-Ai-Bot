import datetime
import calendar
from typing import Optional, Tuple

from .enums import Granularity, TimeIntentType
from .models import (
    BaseTimeIntent,
    TimeSettings,
    CalculatedDateRange,
    LastNDaysIntent,
    LastNWeeksIntent,
    LastNMonthsIntent,
    LastNYearsIntent,
    CurrentDayIntent,
    CurrentWeekIntent,
    CurrentMonthIntent,
    CurrentYearIntent,
    PreviousDayIntent,
    PreviousWeekIntent,
    PreviousMonthIntent,
    PreviousYearIntent,
    DateRangeIntent,
    YearRangeIntent,
    MonthRangeIntent,
    YearComparisonIntent,
    MonthComparisonIntent,
    CurrentQuarterIntent,
    PreviousQuarterIntent,
    QuarterRangeIntent,
    QuarterComparisonIntent,
    GrowthIntent,
    TrendIntent,
    RunningTotalIntent,
    YTDIntent,
    MTDIntent,
    QTDIntent,
    FiscalYTDIntent,
)


class DateCalculator:
    """Computes date ranges and temporal boundaries based on intents and settings."""

    def __init__(self, settings: TimeSettings):
        self.settings = settings

    def calculate(self, intent: BaseTimeIntent) -> CalculatedDateRange:
        ref_date = getattr(intent, "reference_date", None) or datetime.date.today()

        if isinstance(intent, LastNDaysIntent):
            return self.calculate_last_n_days(intent, ref_date)
        elif isinstance(intent, LastNWeeksIntent):
            return self.calculate_last_n_weeks(intent, ref_date)
        elif isinstance(intent, LastNMonthsIntent):
            return self.calculate_last_n_months(intent, ref_date)
        elif isinstance(intent, LastNYearsIntent):
            return self.calculate_last_n_years(intent, ref_date)
        elif isinstance(intent, CurrentDayIntent):
            return self.calculate_current_day(intent, ref_date)
        elif isinstance(intent, CurrentWeekIntent):
            return self.calculate_current_week(intent, ref_date)
        elif isinstance(intent, CurrentMonthIntent):
            return self.calculate_current_month(intent, ref_date)
        elif isinstance(intent, CurrentYearIntent):
            return self.calculate_current_year(intent, ref_date)
        elif isinstance(intent, PreviousDayIntent):
            return self.calculate_previous_day(intent, ref_date)
        elif isinstance(intent, PreviousWeekIntent):
            return self.calculate_previous_week(intent, ref_date)
        elif isinstance(intent, PreviousMonthIntent):
            return self.calculate_previous_month(intent, ref_date)
        elif isinstance(intent, PreviousYearIntent):
            return self.calculate_previous_year(intent, ref_date)
        elif isinstance(intent, DateRangeIntent):
            return self.calculate_date_range(intent, ref_date)
        elif isinstance(intent, YearRangeIntent):
            return self.calculate_year_range(intent, ref_date)
        elif isinstance(intent, MonthRangeIntent):
            return self.calculate_month_range(intent, ref_date)
        elif isinstance(intent, YearComparisonIntent):
            return self.calculate_year_comparison(intent, ref_date)
        elif isinstance(intent, MonthComparisonIntent):
            return self.calculate_month_comparison(intent, ref_date)
        elif isinstance(intent, CurrentQuarterIntent):
            return self.calculate_current_quarter(intent, ref_date)
        elif isinstance(intent, PreviousQuarterIntent):
            return self.calculate_previous_quarter(intent, ref_date)
        elif isinstance(intent, QuarterRangeIntent):
            return self.calculate_quarter_range(intent, ref_date)
        elif isinstance(intent, QuarterComparisonIntent):
            return self.calculate_quarter_comparison(intent, ref_date)
        elif isinstance(intent, YTDIntent):
            return self.calculate_ytd(intent, ref_date)
        elif isinstance(intent, MTDIntent):
            return self.calculate_mtd(intent, ref_date)
        elif isinstance(intent, QTDIntent):
            return self.calculate_qtd(intent, ref_date)
        elif isinstance(intent, FiscalYTDIntent):
            return self.calculate_fiscal_ytd(intent, ref_date)
        elif isinstance(intent, GrowthIntent):
            return self.calculate_growth(intent, ref_date)
        elif isinstance(intent, TrendIntent):
            return self.calculate_trend(intent, ref_date)
        elif isinstance(intent, RunningTotalIntent):
            return self.calculate_running_total(intent, ref_date)

        return CalculatedDateRange(
            start_date=None,
            end_date=None,
            granularity=Granularity.AUTO,
            reference_date=ref_date
        )

    def calculate_last_n_days(self, intent: LastNDaysIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start = ref_date - datetime.timedelta(days=intent.count - 1)
        return CalculatedDateRange(start, ref_date, Granularity.DAY, ref_date)

    def calculate_last_n_weeks(self, intent: LastNWeeksIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start = ref_date - datetime.timedelta(weeks=intent.count) + datetime.timedelta(days=1)
        return CalculatedDateRange(start, ref_date, Granularity.WEEK, ref_date)

    def calculate_last_n_months(self, intent: LastNMonthsIntent, ref_date: datetime.date) -> CalculatedDateRange:
        year, month = ref_date.year, ref_date.month
        for _ in range(intent.count):
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        max_day = calendar.monthrange(year, month)[1]
        start = datetime.date(year, month, min(ref_date.day, max_day))
        return CalculatedDateRange(start, ref_date, Granularity.MONTH, ref_date)

    def calculate_last_n_years(self, intent: LastNYearsIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start = datetime.date(ref_date.year - intent.count + 1, 1, 1)
        end = datetime.date(ref_date.year, 12, 31)
        return CalculatedDateRange(start, end, Granularity.YEAR, ref_date)

    def calculate_current_day(self, intent: CurrentDayIntent, ref_date: datetime.date) -> CalculatedDateRange:
        return CalculatedDateRange(ref_date, ref_date, Granularity.DAY, ref_date)

    def calculate_current_week(self, intent: CurrentWeekIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start = ref_date - datetime.timedelta(days=ref_date.weekday())
        end = start + datetime.timedelta(days=6)
        return CalculatedDateRange(start, end, Granularity.WEEK, ref_date)

    def calculate_current_month(self, intent: CurrentMonthIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start = datetime.date(ref_date.year, ref_date.month, 1)
        max_day = calendar.monthrange(ref_date.year, ref_date.month)[1]
        end = datetime.date(ref_date.year, ref_date.month, max_day)
        return CalculatedDateRange(start, end, Granularity.MONTH, ref_date)

    def calculate_current_year(self, intent: CurrentYearIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start = datetime.date(ref_date.year, 1, 1)
        end = datetime.date(ref_date.year, 12, 31)
        return CalculatedDateRange(start, end, Granularity.YEAR, ref_date)

    def calculate_previous_day(self, intent: PreviousDayIntent, ref_date: datetime.date) -> CalculatedDateRange:
        day = ref_date - datetime.timedelta(days=1)
        return CalculatedDateRange(day, day, Granularity.DAY, ref_date)

    def calculate_previous_week(self, intent: PreviousWeekIntent, ref_date: datetime.date) -> CalculatedDateRange:
        current_week_start = ref_date - datetime.timedelta(days=ref_date.weekday())
        start = current_week_start - datetime.timedelta(weeks=1)
        end = start + datetime.timedelta(days=6)
        return CalculatedDateRange(start, end, Granularity.WEEK, ref_date)

    def calculate_previous_month(self, intent: PreviousMonthIntent, ref_date: datetime.date) -> CalculatedDateRange:
        year, month = ref_date.year, ref_date.month - 1
        if month == 0:
            month = 12
            year -= 1
        start = datetime.date(year, month, 1)
        max_day = calendar.monthrange(year, month)[1]
        end = datetime.date(year, month, max_day)
        return CalculatedDateRange(start, end, Granularity.MONTH, ref_date)

    def calculate_previous_year(self, intent: PreviousYearIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start = datetime.date(ref_date.year - 1, 1, 1)
        end = datetime.date(ref_date.year - 1, 12, 31)
        return CalculatedDateRange(start, end, Granularity.YEAR, ref_date)

    def calculate_date_range(self, intent: DateRangeIntent, ref_date: datetime.date) -> CalculatedDateRange:
        return CalculatedDateRange(intent.start_date, intent.end_date, Granularity.DAY, ref_date)

    def calculate_year_range(self, intent: YearRangeIntent, ref_date: datetime.date) -> CalculatedDateRange:
        return CalculatedDateRange(
            datetime.date(intent.start_year, 1, 1),
            datetime.date(intent.end_year, 12, 31),
            Granularity.YEAR,
            ref_date
        )

    def calculate_month_range(self, intent: MonthRangeIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start = datetime.date(intent.start_year, intent.start_month, 1)
        max_day = calendar.monthrange(intent.end_year, intent.end_month)[1]
        end = datetime.date(intent.end_year, intent.end_month, max_day)
        return CalculatedDateRange(start, end, Granularity.MONTH, ref_date)

    def calculate_year_comparison(self, intent: YearComparisonIntent, ref_date: datetime.date) -> CalculatedDateRange:
        return CalculatedDateRange(
            datetime.date(intent.start_year, 1, 1),
            datetime.date(intent.end_year, 12, 31),
            Granularity.YEAR,
            ref_date
        )

    def calculate_month_comparison(self, intent: MonthComparisonIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start = datetime.date(intent.start_year, intent.start_month, 1)
        max_day = calendar.monthrange(intent.end_year, intent.end_month)[1]
        end = datetime.date(intent.end_year, intent.end_month, max_day)
        return CalculatedDateRange(start, end, Granularity.MONTH, ref_date)

    def calculate_current_quarter(self, intent: CurrentQuarterIntent, ref_date: datetime.date) -> CalculatedDateRange:
        q = (ref_date.month - 1) // 3 + 1
        start_date = datetime.date(ref_date.year, (q - 1) * 3 + 1, 1)
        last_month = q * 3
        last_day = calendar.monthrange(ref_date.year, last_month)[1]
        end_date = datetime.date(ref_date.year, last_month, last_day)
        return CalculatedDateRange(start_date, end_date, Granularity.QUARTER, ref_date)

    def calculate_previous_quarter(self, intent: PreviousQuarterIntent, ref_date: datetime.date) -> CalculatedDateRange:
        q = (ref_date.month - 1) // 3 + 1
        prev_q = q - 1
        prev_y = ref_date.year
        if prev_q == 0:
            prev_q = 4
            prev_y -= 1
        start_date = datetime.date(prev_y, (prev_q - 1) * 3 + 1, 1)
        last_month = prev_q * 3
        last_day = calendar.monthrange(prev_y, last_month)[1]
        end_date = datetime.date(prev_y, last_month, last_day)
        return CalculatedDateRange(start_date, end_date, Granularity.QUARTER, ref_date)

    def calculate_quarter_range(self, intent: QuarterRangeIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start_date = datetime.date(intent.year, (intent.quarter - 1) * 3 + 1, 1)
        last_month = intent.quarter * 3
        last_day = calendar.monthrange(intent.year, last_month)[1]
        end_date = datetime.date(intent.year, last_month, last_day)
        return CalculatedDateRange(start_date, end_date, Granularity.QUARTER, ref_date)

    def calculate_quarter_comparison(self, intent: QuarterComparisonIntent, ref_date: datetime.date) -> CalculatedDateRange:
        q_min = min(intent.q1, intent.q2)
        q_max = max(intent.q1, intent.q2)
        start_date = datetime.date(intent.year, (q_min - 1) * 3 + 1, 1)
        last_month = q_max * 3
        last_day = calendar.monthrange(intent.year, last_month)[1]
        end_date = datetime.date(intent.year, last_month, last_day)
        return CalculatedDateRange(start_date, end_date, Granularity.QUARTER, ref_date)

    def calculate_ytd(self, intent: YTDIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start = datetime.date(ref_date.year, 1, 1)
        return CalculatedDateRange(start, ref_date, Granularity.AUTO, ref_date)

    def calculate_mtd(self, intent: MTDIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start = datetime.date(ref_date.year, ref_date.month, 1)
        return CalculatedDateRange(start, ref_date, Granularity.MONTH, ref_date)

    def calculate_qtd(self, intent: QTDIntent, ref_date: datetime.date) -> CalculatedDateRange:
        quarter_start_month = ((ref_date.month - 1) // 3) * 3 + 1
        start = datetime.date(ref_date.year, quarter_start_month, 1)
        return CalculatedDateRange(start, ref_date, Granularity.QUARTER, ref_date)

    def calculate_fiscal_ytd(self, intent: FiscalYTDIntent, ref_date: datetime.date) -> CalculatedDateRange:
        fy_start_month = self.settings.financial_year_start_month
        if ref_date.month >= fy_start_month:
            start = datetime.date(ref_date.year, fy_start_month, 1)
        else:
            start = datetime.date(ref_date.year - 1, fy_start_month, 1)
        return CalculatedDateRange(start, ref_date, Granularity.AUTO, ref_date)

    def calculate_growth(self, intent: GrowthIntent, ref_date: datetime.date) -> CalculatedDateRange:
        if intent.comparison_type == TimeIntentType.PREVIOUS_YEAR:
            start = datetime.date(ref_date.year - 1, 1, 1)
            end = datetime.date(ref_date.year - 1, 12, 31)
            return CalculatedDateRange(start, end, Granularity.YEAR, ref_date)
        start = datetime.date(ref_date.year, 1, 1)
        return CalculatedDateRange(start, ref_date, Granularity.AUTO, ref_date)

    def calculate_trend(self, intent: TrendIntent, ref_date: datetime.date) -> CalculatedDateRange:
        if intent.limit_years:
            start_date = datetime.date(ref_date.year - intent.limit_years + 1, 1, 1)
            end_date = datetime.date(ref_date.year, 12, 31)
            return CalculatedDateRange(start_date, end_date, intent.granularity, ref_date)
            
        year, month = ref_date.year, ref_date.month
        for _ in range(12):
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        max_day = calendar.monthrange(year, month)[1]
        start = datetime.date(year, month, min(ref_date.day, max_day))
        return CalculatedDateRange(start, ref_date, intent.granularity, ref_date)

    def calculate_running_total(self, intent: RunningTotalIntent, ref_date: datetime.date) -> CalculatedDateRange:
        start = datetime.date(ref_date.year, 1, 1)
        return CalculatedDateRange(start, ref_date, Granularity.AUTO, ref_date)
