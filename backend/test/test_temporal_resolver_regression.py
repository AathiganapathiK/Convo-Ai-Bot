import sys
import os
import datetime
import calendar
import unittest
import re
from typing import Optional, List, Dict, Any, Tuple

# Adjust Python path to resolve packages correctly from the backend directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantic.temporal.models import (
    BaseTimeIntent,
    TimeSettings,
    CalculatedDateRange,
    ResolvedTimePlan,
    TimeCapability,
    TimeResolutionResult,
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
    TrendIntent
)
from semantic.temporal.enums import TimeIntentType, CalendarType, Granularity, TimeStrategyType
from semantic.temporal.detector import TemporalDetector
from semantic.temporal.date_calculator import DateCalculator
from semantic.temporal.time_resolver import TimeResolver
from semantic.sql.temporal_mapper import TemporalMapper


def resolve_question(question: str, reference_date: datetime.date) -> TimeResolutionResult:
    """
    Resolves the question using the production TimeResolver.
    """
    resolver = TimeResolver()
    capability = TimeCapability(
        date_columns=["OrderDate"],
        default_date_column="OrderDate"
    )
    settings = TimeSettings(financial_year_start_month=4)
    return resolver.resolve(
        question=question,
        capability=capability,
        settings=settings,
        reference_date=reference_date
    )


def generate_sql(question: str, intent: BaseTimeIntent, plan: ResolvedTimePlan, ref_date: datetime.date) -> str:
    """
    Deterministic rule-based SQL generator using production mapper.
    """
    date_col = plan.date_column or "OrderDate"
    select_cols = ["SUM(SalesAmount)"]
    where_clauses = []
    group_by_cols = []
    
    # 1. Product Category filtering from question
    q_norm = question.lower()
    if "banian" in q_norm:
        where_clauses.append("Category = 'banian'")
    elif "shirt" in q_norm:
        where_clauses.append("Category = 'shirt'")

    # 2. Date Filtering depending on intent/plan bounds
    if plan.start_date and plan.end_date:
        if plan.end_date.year == 9999:  # e.g., 'after January'
            where_clauses.append(f"{date_col} > '{plan.start_date.isoformat()}'")
        elif plan.start_date.year == 1:  # e.g., 'before March'
            where_clauses.append(f"{date_col} < '{plan.end_date.isoformat()}'")
        elif plan.start_date == plan.end_date:
            date_expr = TemporalMapper.get_sql_expression("mssql", "TIME_DATE", date_col)
            where_clauses.append(f"{date_expr} = '{plan.start_date.isoformat()}'")
        else:
            # Handle special previous month/quarter relative SQL patterns
            if isinstance(intent, PreviousMonthIntent):
                where_clauses.append(f"MONTH({date_col}) = MONTH(DATEADD(month, -1, GETDATE())) AND YEAR({date_col}) = YEAR(DATEADD(month, -1, GETDATE()))")
            elif isinstance(intent, PreviousQuarterIntent):
                where_clauses.append(f"DATEPART(quarter, {date_col}) = DATEPART(quarter, DATEADD(quarter, -1, GETDATE())) AND YEAR({date_col}) = YEAR(DATEADD(quarter, -1, GETDATE()))")
            elif isinstance(intent, CurrentQuarterIntent):
                where_clauses.append(f"DATEPART(quarter, {date_col}) = DATEPART(quarter, GETDATE()) AND YEAR({date_col}) = YEAR(GETDATE())")
            elif isinstance(intent, CurrentMonthIntent):
                where_clauses.append(f"MONTH({date_col}) = MONTH(GETDATE()) AND YEAR({date_col}) = YEAR(GETDATE())")
            elif isinstance(intent, CurrentYearIntent):
                where_clauses.append(f"YEAR({date_col}) = YEAR(GETDATE())")
            elif isinstance(intent, PreviousYearIntent):
                where_clauses.append(f"YEAR({date_col}) = YEAR(DATEADD(year, -1, GETDATE()))")
            elif isinstance(intent, CurrentWeekIntent):
                where_clauses.append(f"DATEPART(week, {date_col}) = DATEPART(week, GETDATE()) AND YEAR({date_col}) = YEAR(GETDATE())")
            elif isinstance(intent, PreviousWeekIntent):
                where_clauses.append(f"DATEPART(week, {date_col}) = DATEPART(week, DATEADD(week, -1, GETDATE())) AND YEAR({date_col}) = YEAR(DATEADD(week, -1, GETDATE()))")
            elif isinstance(intent, CurrentDayIntent):
                where_clauses.append(f"CAST({date_col} AS DATE) = CAST(GETDATE() AS DATE)")
            elif isinstance(intent, PreviousDayIntent):
                where_clauses.append(f"CAST({date_col} AS DATE) = CAST(DATEADD(day, -1, GETDATE()) AS DATE)")
            elif isinstance(intent, LastNDaysIntent):
                where_clauses.append(f"{date_col} >= DATEADD(day, -{intent.count}, CAST(GETDATE() AS DATE))")
            elif isinstance(intent, LastNMonthsIntent):
                where_clauses.append(f"{date_col} >= DATEADD(month, -{intent.count}, CAST(GETDATE() AS DATE))")
            elif isinstance(intent, LastNYearsIntent):
                where_clauses.append(f"{date_col} >= DATEADD(year, -{intent.count}, CAST(GETDATE() AS DATE))")
            elif isinstance(intent, QuarterRangeIntent):
                where_clauses.append(f"DATEPART(quarter, {date_col}) = {intent.quarter} AND YEAR({date_col}) = {intent.year}")
            elif isinstance(intent, QuarterComparisonIntent):
                where_clauses.append(f"DATEPART(quarter, {date_col}) IN ({intent.q1}, {intent.q2}) AND YEAR({date_col}) = {intent.year}")
            elif isinstance(intent, YearRangeIntent):
                if intent.start_year == intent.end_year:
                    where_clauses.append(f"YEAR({date_col}) = {intent.start_year}")
                else:
                    where_clauses.append(f"YEAR({date_col}) BETWEEN {intent.start_year} AND {intent.end_year}")
            elif isinstance(intent, MonthRangeIntent):
                if intent.start_year == intent.end_year and intent.start_month == intent.end_month:
                    where_clauses.append(f"MONTH({date_col}) = {intent.start_month} AND YEAR({date_col}) = {intent.start_year}")
                else:
                    where_clauses.append(f"YEAR({date_col}) = {intent.start_year} AND MONTH({date_col}) BETWEEN {intent.start_month} AND {intent.end_month}")
            elif isinstance(intent, YearComparisonIntent):
                where_clauses.append(f"YEAR({date_col}) IN ({intent.start_year}, {intent.end_year})")
            elif isinstance(intent, MonthComparisonIntent):
                where_clauses.append(f"((YEAR({date_col}) = {intent.start_year} AND MONTH({date_col}) = {intent.start_month}) OR (YEAR({date_col}) = {intent.end_year} AND MONTH({date_col}) = {intent.end_month}))")
            else:
                where_clauses.append(f"{date_col} BETWEEN '{plan.start_date.isoformat()}' AND '{plan.end_date.isoformat()}'")
                
    elif plan.start_date:
        where_clauses.append(f"{date_col} >= '{plan.start_date.isoformat()}'")
    elif plan.end_date:
        where_clauses.append(f"{date_col} <= '{plan.end_date.isoformat()}'")

    # 3. Grouping and Trends
    grouping = plan.grouping
    if isinstance(intent, TrendIntent) and (not grouping or grouping == Granularity.AUTO):
        grouping = Granularity.MONTH

    if grouping and grouping != Granularity.AUTO:
        category_map = {
            Granularity.YEAR: "TIME_YEAR",
            Granularity.QUARTER: "TIME_QUARTER",
            Granularity.MONTH: "TIME_MONTH",
            Granularity.WEEK: "TIME_WEEK",
            Granularity.DAY: "TIME_DAY",
        }
        cat = category_map.get(grouping)
        if cat:
            group_expr = TemporalMapper.get_sql_expression("mssql", cat, date_col)
            select_cols.insert(0, f"{group_expr} AS {grouping.value.capitalize()}")
            group_by_cols.append(group_expr)

    # 4. Comparisons Grouping
    if isinstance(intent, YearComparisonIntent) and not group_by_cols:
        year_expr = TemporalMapper.get_sql_expression("mssql", "TIME_YEAR", date_col)
        select_cols.insert(0, f"{year_expr} AS Year")
        group_by_cols.append(year_expr)
    elif isinstance(intent, MonthComparisonIntent) and not group_by_cols:
        year_expr = TemporalMapper.get_sql_expression("mssql", "TIME_YEAR", date_col)
        month_expr = TemporalMapper.get_sql_expression("mssql", "TIME_MONTH", date_col)
        select_cols.insert(0, f"{year_expr} AS Year, {month_expr} AS Month")
        group_by_cols.extend([year_expr, month_expr])
    elif isinstance(intent, QuarterComparisonIntent) and not group_by_cols:
        q_expr = TemporalMapper.get_sql_expression("mssql", "TIME_QUARTER", date_col)
        select_cols.insert(0, f"{q_expr} AS Quarter")
        group_by_cols.append(q_expr)

    # Construct final query
    sql = f"SELECT {', '.join(select_cols)} FROM Sales"
    if where_clauses:
        sql += f" WHERE {' AND '.join(where_clauses)}"
    if group_by_cols:
        sql += f" GROUP BY {', '.join(group_by_cols)}"
        
    return sql


def validate_sql(question: str, intent: BaseTimeIntent, sql: str, ref_date: datetime.date) -> Tuple[bool, str]:
    """
    Validates that the generated SQL is correct and free of regression bugs.
    """
    sql_upper = sql.upper().replace(" ", "")
    q_lower = question.lower()

    # 1. FAIL if Current Quarter generates MONTH() instead of DATEPART(QUARTER,...)
    if "quarter" in q_lower or isinstance(intent, (CurrentQuarterIntent, PreviousQuarterIntent, QuarterRangeIntent, QuarterComparisonIntent)):
        if "trend" not in q_lower and "qtd" not in q_lower:
            if "MONTH(" in sql.upper() and "DATEPART(QUARTER" not in sql.upper() and "DATEPART(Q," not in sql.upper():
                return False, "Current Quarter query generates MONTH() instead of DATEPART(quarter, ...)"

    # 2. FAIL if Previous Month uses YEAR(GETDATE()) instead of YEAR(DATEADD(month,-1,GETDATE()))
    if "previous month" in q_lower or "last month" in q_lower:
        if "compare" not in q_lower:
            if "YEAR(GETDATE())" in sql_upper:
                return False, "Previous Month query uses YEAR(GETDATE()) instead of YEAR(DATEADD(month,-1,GETDATE()))"

    # 3. FAIL if Previous Quarter uses the wrong year.
    if "previous quarter" in q_lower or "last quarter" in q_lower:
        if ref_date == datetime.date(2026, 1, 15):
            if "2026" in sql or "YEAR(GETDATE())" in sql_upper:
                return False, f"Previous Quarter uses the wrong year (expected 2025, got 2026/GETDATE)"

    # 4. FAIL if Trend query does not group by a time dimension.
    if "trend" in q_lower or "wise" in q_lower:
        if "GROUPBY" not in sql_upper:
            return False, "Trend query does not group by a time dimension (lacks GROUP BY clause)"

        # 5. FAIL if Month-wise trend lacks GROUP BY MONTH.
        if "month" in q_lower or ("trend" in q_lower and "yearly" not in q_lower and "quarterly" not in q_lower and "year" not in q_lower):
            if "GROUPBYMONTH(" not in sql_upper and "MONTH(" not in sql_upper:
                return False, "Month-wise trend lacks GROUP BY MONTH"

        # 6. FAIL if Year-wise trend lacks GROUP BY YEAR.
        if "year" in q_lower:
            if "GROUPBYYEAR(" not in sql_upper and "YEAR(" not in sql_upper:
                return False, "Year-wise trend lacks GROUP BY YEAR"

        # 7. FAIL if Quarter-wise trend lacks GROUP BY QUARTER.
        if "quarter" in q_lower:
            if "GROUPBYDATEPART(QUARTER" not in sql_upper and "DATEPART(QUARTER" not in sql_upper and "DATEPART(Q," not in sql_upper:
                return False, "Quarter-wise trend lacks GROUP BY QUARTER"

    return True, ""


class TestTemporalResolverRegression(unittest.TestCase):
    """
    Unit test class executing validation assertions against groups sequentially.
    """
    def setUp(self):
        self.ref_date = datetime.date(2026, 8, 5)

    def test_regression_suite(self):
        questions_to_test = [
            ("Show current year sales", self.ref_date),
            ("Show previous month sales", self.ref_date),
            ("Show current quarter sales", self.ref_date),
            ("Show yearly sales trend", self.ref_date),
            ("Show previous quarter sales", datetime.date(2026, 1, 15)),
        ]
        for q, ref_date in questions_to_test:
            res = resolve_question(q, ref_date)
            self.assertTrue(res.resolved)
            sql = generate_sql(q, res.intent, res.plan, ref_date)
            passed, reason = validate_sql(q, res.intent, sql, ref_date)
            self.assertTrue(passed, reason)


def run_regression_report():
    print("======================================================")
    print("TEMPORAL RESOLVER REGRESSION REPORT")
    print("======================================================")

    ref_date = datetime.date(2026, 8, 5)
    
    test_groups = {
        "GROUP 1 : CURRENT PERIOD": [
            "Show current year sales",
            "Show current year banian sales",
            "Show current month sales",
            "Show current month banian sales",
            "Show current quarter sales",
            "Show current quarter shirt sales",
            "Show today's sales",
            "Show this week's sales",
            "Show this month's sales",
            "Show this quarter's sales",
        ],
        "GROUP 2 : PREVIOUS PERIOD": [
            "Show previous year sales",
            "Show previous year banian sales",
            "Show previous month sales",
            "Show previous month shirt sales",
            "Show previous quarter sales",
            "Show previous week sales",
            "Show yesterday's sales",
        ],
        "GROUP 3 : RELATIVE PERIOD": [
            "Show last 7 days sales",
            "Show last 30 days sales",
            "Show last 90 days sales",
            "Show last 6 months sales",
            "Show last 12 months sales",
            "Show past 5 years sales",
            "Show last 2 years sales",
        ],
        "GROUP 4 : EXPLICIT YEAR": [
            "Show 2023 sales",
            "Show 2024 sales",
            "Show 2025 sales",
            "Show 2026 sales",
            "Show 2024 banian sales",
        ],
        "GROUP 5 : EXPLICIT MONTH": [
            "Show January sales",
            "Show February sales",
            "Show March sales",
            "Show December sales",
            "Show January 2025 sales",
            "Show March 2024 sales",
        ],
        "GROUP 6 : EXPLICIT QUARTER": [
            "Show Q1 sales",
            "Show Q2 sales",
            "Show Q3 sales",
            "Show Q4 sales",
            "Show Q2 2025 sales",
        ],
        "GROUP 7 : COMPARISON": [
            "Compare current year and previous year sales",
            "Compare this month and last month sales",
            "Compare Q1 and Q2 sales",
            "Compare last year and this year banian sales",
        ],
        "GROUP 8 : TREND": [
            "Show sales trend",
            "Show yearly sales trend",
            "Show monthly sales trend",
            "Show quarterly sales trend",
            "Show last 5 year sales trend",
            "Show month wise banian sales",
            "Show year wise shirt sales",
        ],
        "GROUP 9 : DATE RANGE": [
            "Show sales till today",
            "Show sales from January to March",
            "Show sales between January and June",
            "Show sales after January",
            "Show sales before March",
            "Show sales since 2024",
        ]
    }

    group10_mock_dates = [
        datetime.date(2026, 1, 15),
        datetime.date(2026, 4, 15),
        datetime.date(2026, 7, 15),
        datetime.date(2026, 10, 15)
    ]
    group10_queries = [
        "Show previous month sales",
        "Show previous quarter sales",
        "Show current quarter sales",
        "Show current year sales",
        "Show previous year sales"
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    failed_details = []

    def execute_test(q: str, current_ref: datetime.date) -> None:
        nonlocal total_tests, passed_tests, failed_tests
        total_tests += 1

        res = resolve_question(q, current_ref)
        intent_name = res.intent.__class__.__name__ if res.resolved else "None"
        
        if res.resolved and res.plan and res.plan.start_date and res.plan.end_date:
            period_str = f"{res.plan.start_date.isoformat()} to {res.plan.end_date.isoformat()}"
        else:
            period_str = "None"

        sql = ""
        passed = False
        reason = "Detection / Resolution failed"

        if res.resolved:
            sql = generate_sql(q, res.intent, res.plan, current_ref)
            passed, reason = validate_sql(q, res.intent, sql, current_ref)

        if passed:
            passed_tests += 1
            result_status = "PASS"
        else:
            failed_tests += 1
            result_status = "FAIL"
            failed_details.append((q, reason))

        # Expected check description
        expected_check = "No bugs detected"
        if "quarter" in q.lower() and "trend" not in q.lower():
            expected_check = "Uses DATEPART(quarter, ...)"
        elif "previous month" in q.lower() or "last month" in q.lower():
            expected_check = "Uses YEAR(DATEADD(month, -1, GETDATE()))"
        elif "trend" in q.lower() or "wise" in q.lower():
            expected_check = "Groups by time dimension"

        print("======================================================")
        print(f"Question: {q}")
        print(f"Reference Date: {current_ref.isoformat()}")
        print(f"Resolved Temporal Intent: {intent_name}")
        print(f"Resolved Period: {period_str}")
        print(f"Generated SQL: {sql}")
        print(f"Expected Check: {expected_check}")
        print(f"STATUS: {result_status}")
        if not passed:
            print(f"Reason: {reason}")
        print("======================================================\n")

    # Run groups 1 to 9
    for group_name, queries in test_groups.items():
        print(f"==========================\n{group_name}\n==========================")
        for q in queries:
            execute_test(q, ref_date)

    # Run Group 10
    print("==========================\nGROUP 10 : CALENDAR EDGE CASES\n==========================")
    for mock_today in group10_mock_dates:
        print(f"--- Mocking Today's Date: {mock_today.isoformat()} ---")
        for q in group10_queries:
            execute_test(q, mock_today)

    # Print Final Summary
    pass_pct = round((passed_tests / total_tests) * 100, 2) if total_tests > 0 else 0.0

    print("----------------------------------------")
    print(f"TOTAL TESTS: {total_tests}")
    print(f"PASSED     : {passed_tests}")
    print(f"FAILED     : {failed_tests}")
    print(f"PASS %     : {pass_pct}%")
    if failed_details:
        print("FAILED TESTS:")
        for q, reason in failed_details:
            print(f"- {q} ({reason})")
    print("----------------------------------------")

    if failed_tests > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        unittest.main()
    else:
        run_regression_report()
