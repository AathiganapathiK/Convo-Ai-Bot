import json
from dataclasses import asdict
import datetime
from enum import Enum
from .models import TimeContext
from .enums import TimeStrategyType, TimeIntentType


class TemporalPromptFormatter:
    """Formats TimeContext into a clean text block for LLM prompts, JSON, debug views, or logs."""

    def _get_sql_rule(self, context: TimeContext) -> str | None:
        if not context.intent:
            return None
        
        date_col = context.date_column
        if not date_col:
            return None
        intent = context.intent
        intent_type = getattr(intent, "intent_type", None)
        cls_name = intent.__class__.__name__
        
        if cls_name == "CurrentDayIntent" or intent_type == TimeIntentType.CURRENT_DAY:
            return f"CAST({date_col} AS DATE) = CAST(GETDATE() AS DATE)"
            
        elif cls_name == "PreviousDayIntent" or intent_type == TimeIntentType.PREVIOUS_DAY:
            return f"CAST({date_col} AS DATE) = CAST(DATEADD(day, -1, GETDATE()) AS DATE)"
            
        elif cls_name == "LastNDaysIntent" or intent_type == TimeIntentType.LAST_N_DAYS:
            count = getattr(intent, "count", 1)
            return f"{date_col} >= DATEADD(day, -{count}, CAST(GETDATE() AS DATE))"
            
        elif cls_name == "CurrentWeekIntent" or intent_type == TimeIntentType.CURRENT_WEEK:
            return f"DATEPART(week, {date_col}) = DATEPART(week, GETDATE()) AND YEAR({date_col}) = YEAR(GETDATE())"
            
        elif cls_name == "PreviousWeekIntent" or intent_type == TimeIntentType.PREVIOUS_WEEK:
            return f"DATEPART(week, {date_col}) = DATEPART(week, DATEADD(week, -1, GETDATE())) AND YEAR({date_col}) = YEAR(DATEADD(week, -1, GETDATE()))"
            
        elif cls_name == "LastNWeeksIntent" or intent_type == TimeIntentType.LAST_N_WEEKS:
            count = getattr(intent, "count", 1)
            return f"{date_col} >= DATEADD(week, -{count}, CAST(GETDATE() AS DATE))"
            
        elif cls_name == "CurrentMonthIntent" or intent_type == TimeIntentType.CURRENT_MONTH:
            return f"MONTH({date_col}) = MONTH(GETDATE()) AND YEAR({date_col}) = YEAR(GETDATE())"
            
        elif cls_name == "PreviousMonthIntent" or intent_type == TimeIntentType.PREVIOUS_MONTH:
            return f"MONTH({date_col}) = MONTH(DATEADD(month, -1, GETDATE())) AND YEAR({date_col}) = YEAR(DATEADD(month, -1, GETDATE()))"
            
        elif cls_name == "LastNMonthsIntent" or intent_type == TimeIntentType.LAST_N_MONTHS:
            count = getattr(intent, "count", 1)
            return f"{date_col} >= DATEADD(month, -{count}, CAST(GETDATE() AS DATE))"
            
        elif cls_name == "CurrentQuarterIntent" or intent_type == TimeIntentType.CURRENT_QUARTER:
            return f"DATEPART(quarter, {date_col}) = DATEPART(quarter, GETDATE()) AND YEAR({date_col}) = YEAR(GETDATE())"
            
        elif cls_name == "PreviousQuarterIntent" or intent_type == TimeIntentType.PREVIOUS_QUARTER:
            return (
                f"DATEPART(quarter, {date_col}) = DATEPART(quarter, DATEADD(quarter, -1, GETDATE()))\n"
                f"AND YEAR({date_col}) = YEAR(DATEADD(quarter, -1, GETDATE()))"
            )
            
        elif cls_name == "QuarterRangeIntent" or intent_type == TimeIntentType.QUARTER_RANGE:
            quarter = getattr(intent, "quarter", 1)
            year = getattr(intent, "year", 2026)
            return f"DATEPART(quarter, {date_col}) = {quarter} AND YEAR({date_col}) = {year}"
            
        elif cls_name == "QuarterComparisonIntent" or intent_type == TimeIntentType.QUARTER_COMPARISON:
            q1 = getattr(intent, "q1", 1)
            q2 = getattr(intent, "q2", 2)
            year = getattr(intent, "year", 2026)
            return f"DATEPART(quarter, {date_col}) IN ({q1}, {q2}) AND YEAR({date_col}) = {year}"
            
        elif cls_name == "CurrentYearIntent" or intent_type == TimeIntentType.CURRENT_YEAR:
            return f"YEAR({date_col}) = YEAR(GETDATE())"
            
        elif cls_name == "PreviousYearIntent" or intent_type == TimeIntentType.PREVIOUS_YEAR:
            return f"YEAR({date_col}) = YEAR(DATEADD(year, -1, GETDATE()))"
            
        elif cls_name == "LastNYearsIntent" or intent_type == TimeIntentType.LAST_N_YEARS:
            count = getattr(intent, "count", 1)
            return f"{date_col} >= DATEADD(year, -{count}, CAST(GETDATE() AS DATE))"
            
        elif cls_name == "YearRangeIntent" or intent_type == TimeIntentType.YEAR_RANGE:
            start_year = getattr(intent, "start_year", 2026)
            end_year = getattr(intent, "end_year", 2026)
            if start_year == end_year:
                return f"YEAR({date_col}) = {start_year}"
            else:
                return f"YEAR({date_col}) BETWEEN {start_year} AND {end_year}"
                
        elif cls_name == "MonthRangeIntent" or intent_type == TimeIntentType.MONTH_RANGE:
            start_year = getattr(intent, "start_year", 2026)
            end_year = getattr(intent, "end_year", 2026)
            start_month = getattr(intent, "start_month", 1)
            end_month = getattr(intent, "end_month", 1)
            if start_year == end_year and start_month == end_month:
                return f"MONTH({date_col}) = {start_month} AND YEAR({date_col}) = {start_year}"
            else:
                return f"YEAR({date_col}) = {start_year} AND MONTH({date_col}) BETWEEN {start_month} AND {end_month}"
                
        elif cls_name == "YearComparisonIntent" or intent_type == TimeIntentType.YEAR_COMPARISON:
            start_year = getattr(intent, "start_year", 2025)
            end_year = getattr(intent, "end_year", 2026)
            return f"YEAR({date_col}) IN ({start_year}, {end_year})"
            
        elif cls_name == "MonthComparisonIntent" or intent_type == TimeIntentType.MONTH_COMPARISON:
            start_year = getattr(intent, "start_year", 2025)
            start_month = getattr(intent, "start_month", 1)
            end_year = getattr(intent, "end_year", 2026)
            end_month = getattr(intent, "end_month", 1)
            return f"((YEAR({date_col}) = {start_year} AND MONTH({date_col}) = {start_month}) OR (YEAR({date_col}) = {end_year} AND MONTH({date_col}) = {end_month}))"
            
        elif cls_name == "DateRangeIntent" or intent_type == TimeIntentType.DATE_RANGE:
            start_date = getattr(intent, "start_date", None)
            end_date = getattr(intent, "end_date", None)
            if start_date and end_date:
                return f"{date_col} BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'"
            elif start_date:
                return f"{date_col} >= '{start_date.isoformat()}'"
            elif end_date:
                return f"{date_col} <= '{end_date.isoformat()}'"
                
        elif cls_name == "YTDIntent" or intent_type == TimeIntentType.YTD:
            return f"YEAR({date_col}) = YEAR(GETDATE()) AND {date_col} <= GETDATE()"
            
        elif cls_name == "MTDIntent" or intent_type == TimeIntentType.MTD:
            return f"MONTH({date_col}) = MONTH(GETDATE()) AND YEAR({date_col}) = YEAR(GETDATE()) AND {date_col} <= GETDATE()"
            
        elif cls_name == "QTDIntent" or intent_type == TimeIntentType.QTD:
            return f"DATEPART(quarter, {date_col}) = DATEPART(quarter, GETDATE()) AND YEAR({date_col}) = YEAR(GETDATE()) AND {date_col} <= GETDATE()"
            
        elif cls_name == "FiscalYTDIntent" or intent_type == TimeIntentType.FISCAL_YTD:
            if context.start_date and context.end_date:
                return f"{date_col} BETWEEN '{context.start_date.isoformat()}' AND '{context.end_date.isoformat()}'"
            elif context.start_date:
                return f"{date_col} >= '{context.start_date.isoformat()}'"
            elif context.end_date:
                return f"{date_col} <= '{context.end_date.isoformat()}'"
                
        return None

    def format(self, context: TimeContext, style: str = "llm") -> str:
        if style == "json":
            def default_serializer(obj):
                if isinstance(obj, (datetime.date, datetime.datetime)):
                    return obj.isoformat()
                if isinstance(obj, Enum):
                    return obj.value
                if hasattr(obj, "__class__") and obj.__class__.__module__ != "builtins" and not isinstance(obj, (list, dict, set, tuple)):
                    return obj.__class__.__name__
                return str(obj)
            return json.dumps(asdict(context), default=default_serializer, indent=2)

        elif style == "logs":
            intent_name = context.intent.__class__.__name__ if context.intent else "None"
            start = context.start_date.isoformat() if context.start_date else "None"
            end = context.end_date.isoformat() if context.end_date else "None"
            warnings_str = ",".join(context.warnings) if context.warnings else "None"
            strategy_val = context.strategy.value if context.strategy else "None"
            return f"intent={intent_name} strategy={strategy_val} start_date={start} end_date={end} is_partial={context.is_partial} warnings={warnings_str}"

        elif style == "debug":
            intent_name = context.intent.__class__.__name__ if context.intent else "None"
            strategy_val = context.strategy.value if context.strategy else "None"
            lines = [
                "[DEBUG] Temporal Engine TimeContext Details:",
                f"  - Intent: {intent_name}",
                f"  - Strategy: {strategy_val}",
                f"  - Date Column: {context.date_column or 'None'}",
                f"  - Calendar Table: {context.calendar_table or 'None'}",
                f"  - Snapshot Columns: {', '.join(context.snapshot_columns) if context.snapshot_columns else 'None'}",
                f"  - Date Range: {context.start_date or 'None'} to {context.end_date or 'None'}",
                f"  - Grouping / Comparison: {context.grouping.value if context.grouping else 'None'} / {context.comparison or 'None'}",
                f"  - Settings: timezone={context.timezone}, locale={context.locale}, start_month={context.financial_year_start_month}",
                f"  - Warnings: {context.warnings or 'None'}"
            ]
            return "\n".join(lines)

        else:  # "llm" style (default)
            lines = ["Temporal Context:"]
            
            # 1. Intent & Strategy
            intent_name = context.intent.__class__.__name__ if context.intent else "None"
            strategy_val = context.strategy.value if context.strategy else "None"
            lines.append(f"Intent: {intent_name}")
            if context.intent and hasattr(context.intent, "intent_type") and context.intent.intent_type:
                lines.append(f"Intent Type: {context.intent.intent_type.value}")
            lines.append(f"Strategy: {strategy_val}")

            # 2. Strategy specific details
            if context.strategy != TimeStrategyType.SNAPSHOT and context.date_column:
                lines.append(f"Date Column: {context.date_column}")
            if context.calendar_table:
                lines.append(f"Calendar Table: {context.calendar_table}")
            if context.snapshot_columns:
                cols_str = ", ".join(context.snapshot_columns)
                lines.append(f"Snapshot Columns: {cols_str}")

            # 3. Dates & Grouping / Granularity
            if context.strategy != TimeStrategyType.SNAPSHOT:
                if context.start_date:
                    lines.append(f"Start Date: {context.start_date.isoformat()}")
                if context.end_date:
                    lines.append(f"End Date: {context.end_date.isoformat()}")
            if context.grouping:
                lines.append(f"Grouping: {context.grouping.value}")
                lines.append(f"Granularity: {context.grouping.value}")
            if context.comparison:
                lines.append(f"Comparison: {context.comparison}")

            # 4. Reference Date
            ref_date = getattr(context.intent, "reference_date", None) or datetime.date.today()
            lines.append(f"Reference Date: {ref_date.isoformat()}")

            # 5. SQL Rule (only for non-SNAPSHOT strategies)
            if context.strategy != TimeStrategyType.SNAPSHOT:
                sql_rule = self._get_sql_rule(context)
                if sql_rule:
                    lines.append(f"SQL Rule:\n{sql_rule}")

            # 6. Settings/Environment context
            if context.calendar_type:
                lines.append(f"Calendar Type: {context.calendar_type.value}")
            if context.financial_year_start_month is not None:
                lines.append(f"Financial Year Start Month: {context.financial_year_start_month}")
            lines.append(f"Timezone: {context.timezone}")
            lines.append(f"Locale: {context.locale}")

            # 7. Partial/Graceful degradation warning
            if context.is_partial:
                lines.append("Warning: Requested period exceeds available data.")
                if context.warnings:
                    for w in context.warnings:
                        lines.append(f"- {w}")

            content = "\n".join(lines)
            
            # Wrap in the full 59-character prompt section headers
            return f"\n===========================================================\nTEMPORAL CONTEXT\n===========================================================\n\n{content}\n"
