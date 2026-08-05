import json
from dataclasses import asdict
import datetime
from enum import Enum
from .models import TimeContext


class TemporalPromptFormatter:
    """Formats TimeContext into a clean text block for LLM prompts, JSON, debug views, or logs."""

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
            lines.append(f"Strategy: {strategy_val}")

            # 2. Strategy specific details
            if context.date_column:
                lines.append(f"Date Column: {context.date_column}")
            if context.calendar_table:
                lines.append(f"Calendar Table: {context.calendar_table}")
            if context.snapshot_columns:
                cols_str = ", ".join(context.snapshot_columns)
                lines.append(f"Snapshot Columns: {cols_str}")

            # 3. Dates & Grouping
            if context.start_date:
                lines.append(f"Start Date: {context.start_date.isoformat()}")
            if context.end_date:
                lines.append(f"End Date: {context.end_date.isoformat()}")
            if context.grouping:
                lines.append(f"Grouping: {context.grouping.value}")
            if context.comparison:
                lines.append(f"Comparison: {context.comparison}")

            # 4. Settings/Environment context
            if context.calendar_type:
                lines.append(f"Calendar Type: {context.calendar_type.value}")
            if context.financial_year_start_month is not None:
                lines.append(f"Financial Year Start Month: {context.financial_year_start_month}")
            lines.append(f"Timezone: {context.timezone}")
            lines.append(f"Locale: {context.locale}")

            # 5. Partial/Graceful degradation warning
            if context.is_partial:
                lines.append("Warning: Requested period exceeds available data.")
                if context.warnings:
                    for w in context.warnings:
                        lines.append(f"- {w}")

            content = "\n".join(lines)
            
            # Wrap in the full 59-character prompt section headers
            return f"\n===========================================================\nTEMPORAL CONTEXT\n===========================================================\n\n{content}\n"
