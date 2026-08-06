import datetime
from typing import Optional, Dict, Any

from .tokenizer import TimeTokenizer
from .normalizer import TimeNormalizer
from .parser import TimeParser
from .models import (
    BaseTimeIntent,
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
    YearComparisonIntent,
    MonthRangeIntent,
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
from .enums import TimeIntentType, Granularity

class TemporalDetector:
    """
    Main orchestrator for detecting temporal intents from user queries.
    Pipeline: Question -> Tokenizer -> Normalizer -> Parser -> DetectedTimeExpression -> TimeIntent
    """
    def __init__(self):
        self.tokenizer = TimeTokenizer()
        self.normalizer = TimeNormalizer()
        self.parser = TimeParser()

    def detect(self, question: str, reference_date: Optional[datetime.date] = None) -> Optional[BaseTimeIntent]:
        if not question:
            return None
            
        # 1. Tokenizer
        tokens = self.tokenizer.tokenize(question)
        if not tokens:
            return None
            
        # 2. Normalizer
        normalized_text = self.normalizer.normalize(tokens)
        if not normalized_text:
            return None
            
        # 3. Parser -> DetectedTimeExpression
        expression = self.parser.parse(normalized_text, tokens)
        if not expression:
            return None
            
        # 4. Map to TimeIntent subclass
        intent_type = expression.intent
        meta = expression.metadata
        ref_year = reference_date.year if reference_date else datetime.date.today().year
        
        if intent_type == TimeIntentType.LAST_N_YEARS:
            return LastNYearsIntent(count=meta.get("count", 1), reference_date=reference_date)
        elif intent_type == TimeIntentType.LAST_N_MONTHS:
            return LastNMonthsIntent(count=meta.get("count", 1), reference_date=reference_date)
        elif intent_type == TimeIntentType.LAST_N_WEEKS:
            return LastNWeeksIntent(count=meta.get("count", 1), reference_date=reference_date)
        elif intent_type == TimeIntentType.LAST_N_DAYS:
            return LastNDaysIntent(count=meta.get("count", 1), reference_date=reference_date)
            
        elif intent_type == TimeIntentType.CURRENT_YEAR:
            return CurrentYearIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.CURRENT_MONTH:
            return CurrentMonthIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.CURRENT_WEEK:
            return CurrentWeekIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.CURRENT_DAY:
            return CurrentDayIntent(reference_date=reference_date)
            
        elif intent_type == TimeIntentType.PREVIOUS_YEAR:
            return PreviousYearIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.PREVIOUS_MONTH:
            return PreviousMonthIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.PREVIOUS_WEEK:
            return PreviousWeekIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.PREVIOUS_DAY:
            return PreviousDayIntent(reference_date=reference_date)
            
        elif intent_type == TimeIntentType.YEAR_RANGE:
            return YearRangeIntent(
                start_year=meta.get("start_year", ref_year),
                end_year=meta.get("end_year", ref_year),
                reference_date=reference_date
            )
        elif intent_type == TimeIntentType.YEAR_COMPARISON:
            if meta.get("relative"):
                return YearComparisonIntent(
                    start_year=ref_year - 1,
                    end_year=ref_year
                )
            return YearComparisonIntent(
                start_year=meta.get("start_year", ref_year),
                end_year=meta.get("end_year", ref_year)
            )
        elif intent_type == TimeIntentType.MONTH_COMPARISON:
            if meta.get("relative"):
                prev_month = reference_date.month - 1
                prev_year = reference_date.year
                if prev_month == 0:
                    prev_month = 12
                    prev_year -= 1
                return MonthComparisonIntent(
                    start_month=prev_month,
                    start_year=prev_year,
                    end_month=reference_date.month,
                    end_year=reference_date.year
                )
            return MonthComparisonIntent(
                start_month=meta.get("start_month", 1),
                start_year=meta.get("start_year", ref_year),
                end_month=meta.get("end_month", 1),
                end_year=meta.get("end_year", ref_year)
            )
        elif intent_type == TimeIntentType.MONTH_RANGE:
            start_y = meta.get("start_year")
            end_y = meta.get("end_year")
            if start_y is None and end_y is None:
                start_y = ref_year
                end_y = ref_year
            elif start_y is None:
                start_y = end_y
            elif end_y is None:
                end_y = start_y
            return MonthRangeIntent(
                start_month=meta.get("start_month", 1),
                start_year=start_y,
                end_month=meta.get("end_month", 1),
                end_year=end_y,
                reference_date=reference_date
            )
        elif intent_type == TimeIntentType.CURRENT_QUARTER:
            return CurrentQuarterIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.PREVIOUS_QUARTER:
            return PreviousQuarterIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.QUARTER_RANGE:
            return QuarterRangeIntent(
                quarter=meta.get("quarter", 1),
                year=meta.get("year") or ref_year,
                reference_date=reference_date
            )
        elif intent_type == TimeIntentType.QUARTER_COMPARISON:
            return QuarterComparisonIntent(
                q1=meta.get("q1", 1),
                q2=meta.get("q2", 2),
                year=meta.get("year") or ref_year,
                reference_date=reference_date
            )
        elif intent_type == TimeIntentType.DATE_RANGE:
            if meta.get("is_since"):
                return DateRangeIntent(
                    start_date=datetime.date(meta.get("start_year"), 1, 1),
                    end_date=reference_date,
                    reference_date=reference_date
                )
            elif meta.get("is_before"):
                m_num = meta.get("end_month")
                prev_month = m_num - 1
                prev_year = ref_year
                if prev_month == 0:
                    prev_month = 12
                    prev_year -= 1
                import calendar
                last_day = calendar.monthrange(prev_year, prev_month)[1]
                end_date = datetime.date(prev_year, prev_month, last_day)
                return DateRangeIntent(
                    start_date=datetime.date(1, 1, 1),
                    end_date=end_date,
                    reference_date=reference_date
                )
            elif meta.get("is_after"):
                start_month = meta.get("start_month") + 1
                start_year = ref_year
                if start_month > 12:
                    start_month = 1
                    start_year += 1
                return DateRangeIntent(
                    start_date=datetime.date(start_year, start_month, 1),
                    end_date=datetime.date(9999, 12, 31),
                    reference_date=reference_date
                )
            elif meta.get("is_till_today"):
                return DateRangeIntent(
                    start_date=datetime.date(1970, 1, 1),
                    end_date=reference_date,
                    reference_date=reference_date
                )
            return DateRangeIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.YTD:
            return YTDIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.MTD:
            return MTDIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.QTD:
            return QTDIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.FISCAL_YTD:
            return FiscalYTDIntent(reference_date=reference_date)
        elif intent_type == TimeIntentType.YOY_GROWTH:
            return GrowthIntent(
                comparison_type=TimeIntentType.PREVIOUS_YEAR,
                reference_date=reference_date
            )
        elif intent_type == TimeIntentType.TREND:
            return TrendIntent(
                granularity=meta.get("granularity", Granularity.AUTO),
                limit_years=meta.get("limit_years"),
                reference_date=reference_date
            )
        elif intent_type == TimeIntentType.RUNNING_TOTAL:
            return RunningTotalIntent(reference_date=reference_date)
            
        return None
