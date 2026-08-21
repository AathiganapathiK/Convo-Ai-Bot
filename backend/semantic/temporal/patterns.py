import re
from typing import Dict, Any, Callable, List
from .enums import TimeIntentType, Granularity

class TemporalPattern:
    """
    Represents a specific temporal pattern matching definition.
    """
    def __init__(
        self,
        name: str,
        regex_pattern: str,
        intent_type: TimeIntentType,
        extractor: Callable[[re.Match], Dict[str, Any]],
        confidence: float = 0.95
    ):
        self.name = name
        self.regex = re.compile(regex_pattern, re.IGNORECASE)
        self.intent_type = intent_type
        self.extractor = extractor
        self.confidence = confidence

MONTH_MAP = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}

def extract_last_n(m: re.Match) -> Dict[str, Any]:
    return {"count": int(m.group(1))}

def extract_year_range(m: re.Match) -> Dict[str, Any]:
    return {
        "start_year": int(m.group("start")),
        "end_year": int(m.group("end"))
    }

def extract_month_range(m: re.Match) -> Dict[str, Any]:
    start_m = MONTH_MAP.get(m.group("start_m").lower())
    end_m = MONTH_MAP.get(m.group("end_m").lower())
    
    # Extract year matches
    start_y = m.group("start_y") if "start_y" in m.groupdict() else None
    end_y = m.group("end_y") if "end_y" in m.groupdict() else None
    
    return {
        "start_month": start_m,
        "start_year": int(start_y) if start_y else None,
        "end_month": end_m,
        "end_year": int(end_y) if end_y else None
    }

def extract_trend(m: re.Match) -> Dict[str, Any]:
    text = m.string.lower()
    granularity = Granularity.AUTO
    if "year" in text or "yearly" in text:
        granularity = Granularity.YEAR
    elif "month" in text or "monthly" in text:
        granularity = Granularity.MONTH
    elif "quarter" in text or "quarterly" in text:
        granularity = Granularity.QUARTER
        
    limit_years = None
    m_limit = re.search(r"\b(?:last|past)\s+(\d+)\s+years?\b", text)
    if m_limit:
        limit_years = int(m_limit.group(1))
        
    return {
        "granularity": granularity,
        "limit_years": limit_years
    }

# Define the central library of patterns.
# Checked sequentially in priority order.
TEMPORAL_PATTERNS: List[TemporalPattern] = [
    # 1. Year Comparisons (Check first to avoid matching simple ranges)
    TemporalPattern(
        name="year_comparison_vs",
        regex_pattern=r"\b(?P<start>\d{4})\s+(?:vs|versus)\s+(?P<end>\d{4})\b",
        intent_type=TimeIntentType.YEAR_COMPARISON,
        extractor=extract_year_range,
        confidence=0.98
    ),
    TemporalPattern(
        name="year_comparison_compare_and",
        regex_pattern=r"\b(?:compare|comparison)\s+(?P<start>\d{4})\s+(?:and|with|to)\s+(?P<end>\d{4})\b",
        intent_type=TimeIntentType.YEAR_COMPARISON,
        extractor=extract_year_range,
        confidence=0.98
    ),
    TemporalPattern(
        name="year_comparison_explicit",
        regex_pattern=r"\b(?:compare|comparison|vs|versus)\b.*\bbetween\s+(?P<start>\d{4})\s+and\s+(?P<end>\d{4})\b",
        intent_type=TimeIntentType.YEAR_COMPARISON,
        extractor=extract_year_range,
        confidence=0.98
    ),
    TemporalPattern(
        name="year_comparison_suffix",
        regex_pattern=r"\bbetween\s+(?P<start>\d{4})\s+and\s+(?P<end>\d{4})\b.*\b(?:compare|comparison|vs|versus)\b",
        intent_type=TimeIntentType.YEAR_COMPARISON,
        extractor=extract_year_range,
        confidence=0.98
    ),

    # 1.5 Quarter & Relative Comparisons
    TemporalPattern(
        name="quarter_comparison",
        regex_pattern=r"\b(?:compare\s+)?q(?P<q1>[1-4])\s*(?:and|with|to|vs|versus)\s*q(?P<q2>[1-4])\b",
        intent_type=TimeIntentType.QUARTER_COMPARISON,
        extractor=lambda m: {"q1": int(m.group("q1")), "q2": int(m.group("q2"))},
        confidence=0.98
    ),
    TemporalPattern(
        name="relative_year_comparison",
        regex_pattern=r"\bcompare\s+(?:this|current)\s+year\s+(?:and|with|to)\s+(?:last|previous)\s+year\b|\bcompare\s+(?:last|previous)\s+year\s+(?:and|with|to)\s+(?:this|current)\s+year\b",
        intent_type=TimeIntentType.YEAR_COMPARISON,
        extractor=lambda m: {"relative": True},
        confidence=0.98
    ),
    TemporalPattern(
        name="relative_month_comparison",
        regex_pattern=r"\bcompare\s+(?:this|current)\s+month\s+(?:and|with|to)\s+(?:last|previous)\s+month\b|\bcompare\s+(?:last|previous)\s+month\s+(?:and|with|to)\s+(?:this|current)\s+month\b",
        intent_type=TimeIntentType.MONTH_COMPARISON,
        extractor=lambda m: {"relative": True},
        confidence=0.98
    ),
    TemporalPattern(
        name="quarter_range",
        regex_pattern=r"\bq(?P<quarter>[1-4])\b(?:\s+(?P<year>\d{4}))?",
        intent_type=TimeIntentType.QUARTER_RANGE,
        extractor=lambda m: {"quarter": int(m.group("quarter")), "year": int(m.group("year")) if m.group("year") else None},
        confidence=0.97
    ),
    TemporalPattern(
        name="current_quarter",
        regex_pattern=r"\b(?:current|this)\s+quarter\b",
        intent_type=TimeIntentType.CURRENT_QUARTER,
        extractor=lambda m: {},
        confidence=0.95
    ),
    TemporalPattern(
        name="previous_quarter",
        regex_pattern=r"\b(?:previous|last)\s+quarter\b",
        intent_type=TimeIntentType.PREVIOUS_QUARTER,
        extractor=lambda m: {},
        confidence=0.95
    ),

    # 2. Month Ranges (Check before Year Ranges)
    TemporalPattern(
        name="month_range_from_to",
        regex_pattern=r"\bfrom\s+(?P<start_m>january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b(?:\s+(?P<start_y>\d{4}))?\s+to\s+(?P<end_m>january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b(?:\s+(?P<end_y>\d{4}))?",
        intent_type=TimeIntentType.MONTH_RANGE,
        extractor=extract_month_range,
        confidence=0.96
    ),
    TemporalPattern(
        name="month_range_between",
        regex_pattern=r"\bbetween\s+(?P<start_m>january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b(?:\s+(?P<start_y>\d{4}))?\s+and\s+(?P<end_m>january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b(?:\s+(?P<end_y>\d{4}))?",
        intent_type=TimeIntentType.MONTH_RANGE,
        extractor=extract_month_range,
        confidence=0.96
    ),
    TemporalPattern(
        name="single_month_year",
        regex_pattern=r"\b(?P<month>january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(?P<year>\d{4})\b",
        intent_type=TimeIntentType.MONTH_RANGE,
        extractor=lambda m: {
            "start_month": MONTH_MAP[m.group("month").lower()],
            "start_year": int(m.group("year")),
            "end_month": MONTH_MAP[m.group("month").lower()],
            "end_year": int(m.group("year"))
        },
        confidence=0.97
    ),
    TemporalPattern(
        name="single_month",
        regex_pattern=r"\b(?P<month>january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b",
        intent_type=TimeIntentType.MONTH_RANGE,
        extractor=lambda m: {
            "start_month": MONTH_MAP[m.group("month").lower()],
            "end_month": MONTH_MAP[m.group("month").lower()]
        },
        confidence=0.95
    ),
    
    # 3. Year Ranges
    TemporalPattern(
        name="year_range_between",
        regex_pattern=r"\bbetween\s+(?P<start>\d{4})\s+and\s+(?P<end>\d{4})\b",
        intent_type=TimeIntentType.YEAR_RANGE,
        extractor=extract_year_range,
        confidence=0.96
    ),
    TemporalPattern(
        name="year_range_from_to",
        regex_pattern=r"\bfrom\s+(?P<start>\d{4})\s+to\s+(?P<end>\d{4})\b",
        intent_type=TimeIntentType.YEAR_RANGE,
        extractor=extract_year_range,
        confidence=0.96
    ),
    TemporalPattern(
        name="year_range_hyphen",
        regex_pattern=r"\b(?P<start>\d{4})\s*-\s*(?P<end>\d{4})\b",
        intent_type=TimeIntentType.YEAR_RANGE,
        extractor=extract_year_range,
        confidence=0.96
    ),

    # 3.5 Single Year and Range Modifiers
    TemporalPattern(
        name="since_year",
        regex_pattern=r"\bsince\s+(?P<year>\d{4})\b",
        intent_type=TimeIntentType.DATE_RANGE,
        extractor=lambda m: {"start_year": int(m.group("year")), "is_since": True},
        confidence=0.95
    ),
    TemporalPattern(
        name="before_month",
        regex_pattern=r"\bbefore\s+(?P<month>january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b",
        intent_type=TimeIntentType.DATE_RANGE,
        extractor=lambda m: {"end_month": MONTH_MAP[m.group("month").lower()], "is_before": True},
        confidence=0.95
    ),
    TemporalPattern(
        name="after_month",
        regex_pattern=r"\bafter\s+(?P<month>january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b",
        intent_type=TimeIntentType.DATE_RANGE,
        extractor=lambda m: {"start_month": MONTH_MAP[m.group("month").lower()], "is_after": True},
        confidence=0.95
    ),
    TemporalPattern(
        name="till_today",
        regex_pattern=r"\b(?:till|to|up\s+to)\s+today\b|\btill\s+now\b",
        intent_type=TimeIntentType.DATE_RANGE,
        extractor=lambda m: {"is_till_today": True},
        confidence=0.95
    ),
    TemporalPattern(
        name="single_year",
        regex_pattern=r"\b(?P<year>202[3-6])\b",
        intent_type=TimeIntentType.YEAR_RANGE,
        extractor=lambda m: {"start_year": int(m.group("year")), "end_year": int(m.group("year"))},
        confidence=0.90
    ),

    # 4. Last N Days/Weeks/Months/Years (including rolling months, supports singulars like "1 year", "1 month")
    TemporalPattern(
        name="last_n_years",
        regex_pattern=r"\bpast\s+(\d+)\s+years?\b",
        intent_type=TimeIntentType.LAST_N_YEARS,
        extractor=extract_last_n,
        confidence=0.98
    ),
    TemporalPattern(
        name="last_n_months",
        regex_pattern=r"\bpast\s+(\d+)\s+months?\b",
        intent_type=TimeIntentType.LAST_N_MONTHS,
        extractor=extract_last_n,
        confidence=0.98
    ),
    TemporalPattern(
        name="rolling_n_months",
        regex_pattern=r"\brolling\s+(\d+)\s+months?\b",
        intent_type=TimeIntentType.LAST_N_MONTHS,
        extractor=extract_last_n,
        confidence=0.98
    ),
    TemporalPattern(
        name="last_n_weeks",
        regex_pattern=r"\bpast\s+(\d+)\s+weeks?\b",
        intent_type=TimeIntentType.LAST_N_WEEKS,
        extractor=extract_last_n,
        confidence=0.98
    ),
    TemporalPattern(
        name="last_n_days",
        regex_pattern=r"\bpast\s+(\d+)\s+days?\b",
        intent_type=TimeIntentType.LAST_N_DAYS,
        extractor=extract_last_n,
        confidence=0.98
    ),

    # 5. Modifiers: Running Total, Growth, Trend (Checked after Last N to avoid greedy intercepting of periods)
    TemporalPattern(
        name="running_total",
        regex_pattern=r"\b(?:running\s+total|running\s+sum|cumulative)\b",
        intent_type=TimeIntentType.RUNNING_TOTAL,
        extractor=lambda m: {},
        confidence=0.95
    ),
    TemporalPattern(
        name="yoy_growth",
        regex_pattern=r"\b(?:yoy\s+growth|year\s+over\s+year\s+growth|yoy)\b",
        intent_type=TimeIntentType.YOY_GROWTH,
        extractor=lambda m: {"comparison_type": TimeIntentType.PREVIOUS_YEAR},
        confidence=0.95
    ),
    TemporalPattern(
        name="trend",
        regex_pattern=r"\b(?:trend|trends|historical\s+trend|wise)\b",
        intent_type=TimeIntentType.TREND,
        extractor=extract_trend,
        confidence=0.90
    ),

    # 6. Fixed/Shorthand time frames (FISCAL_YTD checked before YTD)
    TemporalPattern(
        name="fiscal_ytd",
        regex_pattern=r"\b(?:fiscal\s+ytd|fytd)\b",
        intent_type=TimeIntentType.FISCAL_YTD,
        extractor=lambda m: {},
        confidence=0.99
    ),
    TemporalPattern(
        name="ytd",
        regex_pattern=r"\bytd\b",
        intent_type=TimeIntentType.YTD,
        extractor=lambda m: {},
        confidence=0.99
    ),
    TemporalPattern(
        name="mtd",
        regex_pattern=r"\bmtd\b",
        intent_type=TimeIntentType.MTD,
        extractor=lambda m: {},
        confidence=0.99
    ),
    TemporalPattern(
        name="qtd",
        regex_pattern=r"\bqtd\b",
        intent_type=TimeIntentType.QTD,
        extractor=lambda m: {},
        confidence=0.99
    ),

    # 7. Current Day/Week/Month/Year
    TemporalPattern(
        name="current_year",
        regex_pattern=r"\bthis\s+year\b",
        intent_type=TimeIntentType.CURRENT_YEAR,
        extractor=lambda m: {},
        confidence=0.95
    ),
    TemporalPattern(
        name="current_month",
        regex_pattern=r"\bthis\s+month\b",
        intent_type=TimeIntentType.CURRENT_MONTH,
        extractor=lambda m: {},
        confidence=0.95
    ),
    TemporalPattern(
        name="current_week",
        regex_pattern=r"\bthis\s+week\b",
        intent_type=TimeIntentType.CURRENT_WEEK,
        extractor=lambda m: {},
        confidence=0.95
    ),
    TemporalPattern(
        name="current_day",
        regex_pattern=r"\b(?:this\s+day|today)\b",
        intent_type=TimeIntentType.CURRENT_DAY,
        extractor=lambda m: {},
        confidence=0.95
    ),

    # 8. Previous Day/Week/Month/Year
    TemporalPattern(
        name="previous_year",
        regex_pattern=r"\blast\s+year\b",
        intent_type=TimeIntentType.PREVIOUS_YEAR,
        extractor=lambda m: {},
        confidence=0.95
    ),
    TemporalPattern(
        name="previous_month",
        regex_pattern=r"\blast\s+month\b",
        intent_type=TimeIntentType.PREVIOUS_MONTH,
        extractor=lambda m: {},
        confidence=0.95
    ),
    TemporalPattern(
        name="previous_week",
        regex_pattern=r"\blast\s+week\b",
        intent_type=TimeIntentType.PREVIOUS_WEEK,
        extractor=lambda m: {},
        confidence=0.95
    ),
    TemporalPattern(
        name="previous_day",
        regex_pattern=r"\b(?:last\s+day|yesterday)\b",
        intent_type=TimeIntentType.PREVIOUS_DAY,
        extractor=lambda m: {},
        confidence=0.95
    ),
    TemporalPattern(
        name="ppy_ago",
        regex_pattern=r"\b2\s+years?\s+ago\b",
        intent_type=TimeIntentType.PPY,
        extractor=lambda m: {},
        confidence=0.95
    ),
    TemporalPattern(
        name="pppy_ago",
        regex_pattern=r"\b3\s+years?\s+ago\b",
        intent_type=TimeIntentType.PPPY,
        extractor=lambda m: {},
        confidence=0.95
    ),
    TemporalPattern(
        name="ppppy_ago",
        regex_pattern=r"\b4\s+years?\s+ago\b",
        intent_type=TimeIntentType.PPPPY,
        extractor=lambda m: {},
        confidence=0.95
    )
]
