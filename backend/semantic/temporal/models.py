from dataclasses import dataclass, field
import datetime
from typing import Optional, List, Dict, Any

from .enums import TimeIntentType, CalendarType, Granularity, TimeStrategyType, StrategySelectionReason


class BaseTimeIntent:
    """Base class for all time intents."""
    intent_type: TimeIntentType
    calendar_type: CalendarType = CalendarType.AUTO


@dataclass
class LastNDaysIntent(BaseTimeIntent):
    count: int
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.LAST_N_DAYS


@dataclass
class LastNWeeksIntent(BaseTimeIntent):
    count: int
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.LAST_N_WEEKS


@dataclass
class LastNMonthsIntent(BaseTimeIntent):
    count: int
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.LAST_N_MONTHS


@dataclass
class LastNYearsIntent(BaseTimeIntent):
    count: int
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.LAST_N_YEARS


@dataclass
class CurrentDayIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.CURRENT_DAY


@dataclass
class CurrentWeekIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.CURRENT_WEEK


@dataclass
class CurrentMonthIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.CURRENT_MONTH


@dataclass
class CurrentYearIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.CURRENT_YEAR


@dataclass
class PreviousDayIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.PREVIOUS_DAY


@dataclass
class PreviousWeekIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.PREVIOUS_WEEK


@dataclass
class PreviousMonthIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.PREVIOUS_MONTH


@dataclass
class PreviousYearIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.PREVIOUS_YEAR


@dataclass
class DateRangeIntent(BaseTimeIntent):
    start_date: datetime.date
    end_date: datetime.date
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.DATE_RANGE


@dataclass
class YearRangeIntent(BaseTimeIntent):
    start_year: int
    end_year: int
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.YEAR_RANGE


@dataclass
class MonthRangeIntent(BaseTimeIntent):
    start_month: int
    start_year: int
    end_month: int
    end_year: int
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.MONTH_RANGE


@dataclass
class YearComparisonIntent(BaseTimeIntent):
    start_year: int
    end_year: int
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.YEAR_COMPARISON


@dataclass
class MonthComparisonIntent(BaseTimeIntent):
    start_month: int
    start_year: int
    end_month: int
    end_year: int
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.MONTH_COMPARISON


@dataclass
class CurrentQuarterIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.CURRENT_QUARTER


@dataclass
class PreviousQuarterIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.PREVIOUS_QUARTER


@dataclass
class QuarterRangeIntent(BaseTimeIntent):
    quarter: int
    year: int
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.QUARTER_RANGE


@dataclass
class QuarterComparisonIntent(BaseTimeIntent):
    q1: int
    q2: int
    year: int
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.QUARTER_COMPARISON


@dataclass
class GrowthIntent(BaseTimeIntent):
    comparison_type: TimeIntentType
    granularity: Granularity = Granularity.AUTO
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.YOY_GROWTH


@dataclass
class TrendIntent(BaseTimeIntent):
    granularity: Granularity = Granularity.AUTO
    reference_date: Optional[datetime.date] = None
    limit_years: Optional[int] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.TREND


@dataclass
class RunningTotalIntent(BaseTimeIntent):
    granularity: Granularity = Granularity.AUTO
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.RUNNING_TOTAL


@dataclass
class YTDIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.YTD


@dataclass
class MTDIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.MTD


@dataclass
class QTDIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.QTD


@dataclass
class FiscalYTDIntent(BaseTimeIntent):
    reference_date: Optional[datetime.date] = None
    calendar_type: CalendarType = CalendarType.AUTO
    intent_type: TimeIntentType = TimeIntentType.FISCAL_YTD


@dataclass
class TimeResolutionResult:
    """The result of resolving a temporal intent against a datasource strategy."""
    resolved: bool
    intent: Optional[BaseTimeIntent] = None
    plan: Optional["ResolvedTimePlan"] = None
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    is_partial: bool = False
    confidence: float = 0.0
    selection_reason: Optional[StrategySelectionReason] = None
    selection_score: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class YearRange:
    min_year: int
    max_year: int


@dataclass
class DateRange:
    """
    Represents the available date span of a datasource.
    """
    start_date: datetime.date
    end_date: datetime.date


@dataclass
class TimeSettings:
    """Organization-specific temporal settings and preferences."""
    financial_year_start_month: int = 4  # Default to April (Ramraj)
    default_calendar: CalendarType = CalendarType.CALENDAR
    timezone: str = "UTC"
    week_start_day: int = 0  # 0 = Monday, 6 = Sunday
    locale: str = "en_US"


@dataclass
class TimeCapability:
    """Declares the temporal capabilities discovered from a data source schema."""
    date_columns: List[str] = field(default_factory=list)
    snapshot_mapping: Dict[int, str] = field(default_factory=dict)

    # The same bindings with measure_kind and period_scope kept, which
    # snapshot_mapping cannot express - it holds one column per offset, and the
    # sales table has eleven columns across five offsets. Additive on purpose:
    # snapshot_mapping keeps its shape and its consumers, and anything that
    # needs to tell PY from PYTD reads this instead. Populated from
    # semantic_snapshot_mapping; empty when nothing is configured.
    snapshot_bindings: List[Any] = field(default_factory=list)
    snapshot_year_columns: List[str] = field(default_factory=list)
    snapshot_month_columns: List[str] = field(default_factory=list)
    calendar_tables: List[str] = field(default_factory=list)
    default_date_column: Optional[str] = None
    available_year_range: Optional[YearRange] = None
    available_date_range: Optional[DateRange] = None
    supports_time_hierarchy: bool = False

    @property
    def supports_date_columns(self) -> bool:
        return len(self.date_columns) > 0

    @property
    def supports_snapshot_columns(self) -> bool:
        return len(self.snapshot_mapping) > 0

    @property
    def supports_calendar_dimension(self) -> bool:
        return len(self.calendar_tables) > 0

    @property
    def supports_multiple_date_columns(self) -> bool:
        return len(self.date_columns) > 1

    @property
    def supports_fiscal_calendar(self) -> bool:
        return self.supports_date_columns or self.supports_calendar_dimension



@dataclass
class CalculatedDateRange:
    """The result of calculating a temporal date range."""
    start_date: Optional[datetime.date]
    end_date: Optional[datetime.date]
    granularity: Granularity
    reference_date: datetime.date
    is_partial: bool = False
    requested_years: Optional[int] = None
    available_years: Optional[int] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class ResolvedTimePlan:
    """The concrete plan for SQL generator execution."""
    strategy: TimeStrategyType
    date_column: Optional[str] = None
    calendar_table: Optional[str] = None
    snapshot_columns: Optional[List[str]] = None
    grouping: Optional[Granularity] = None
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    reference_date: Optional[datetime.date] = None
    comparison: Optional[str] = None
    is_partial: bool = False
    requested_years: Optional[int] = None
    available_years: Optional[int] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class TimeValidationResult:
    """The result of validating a temporal intent."""
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class DetectedTimeExpression:
    """An expression detected from user input before resolution."""
    text: str
    intent: TimeIntentType
    confidence: float
    matched_tokens: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyCandidate:
    """Represents a potential strategy choice evaluated by the selection engine."""
    strategy: TimeStrategyType
    reason: StrategySelectionReason


@dataclass(frozen=True)
class TimeContext:
    """Unified context carrying all temporal data required for prompt building and SQL generation."""
    intent: BaseTimeIntent
    strategy: TimeStrategyType
    date_column: Optional[str] = None
    calendar_table: Optional[str] = None
    snapshot_columns: List[str] = field(default_factory=list)
    grouping: Optional[Granularity] = None
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    comparison: Optional[str] = None
    calendar_type: CalendarType = CalendarType.CALENDAR
    financial_year_start_month: Optional[int] = None
    timezone: str = "UTC"
    locale: str = "en_US"
    is_partial: bool = False
    warnings: List[str] = field(default_factory=list)





