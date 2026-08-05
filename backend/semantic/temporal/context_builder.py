from typing import Optional, Dict, Any
from .models import TimeResolutionResult, TimeSettings, TimeContext
from .exceptions import ContextBuildException


class TimeContextBuilder:
    """
    Builds a unified TimeContext from a successful TimeResolutionResult
    and active TimeSettings.
    """
    def build(
        self,
        resolution: TimeResolutionResult,
        settings: TimeSettings
    ) -> TimeContext:
        self._validate(resolution)
        context_data = self._map_resolution(resolution)
        context_data = self._merge_settings(context_data, settings)
        return TimeContext(**context_data)

    def _validate(self, resolution: TimeResolutionResult) -> None:
        if not resolution.resolved:
            raise ContextBuildException(
                "Unable to build temporal context because temporal resolution failed. "
                f"Warnings/errors: {resolution.warnings}"
            )
        if not resolution.plan:
            raise ContextBuildException(
                "Unable to build temporal context because resolution did not produce a plan."
            )

    def _map_resolution(self, resolution: TimeResolutionResult) -> Dict[str, Any]:
        """Maps resolution-specific execution details into a raw context dictionary."""
        plan = resolution.plan
        return {
            "intent": resolution.intent,
            "strategy": plan.strategy,
            "date_column": plan.date_column,
            "calendar_table": plan.calendar_table,
            "snapshot_columns": plan.snapshot_columns or [],
            "grouping": plan.grouping,
            "start_date": plan.start_date,
            "end_date": plan.end_date,
            "comparison": plan.comparison,
            "is_partial": resolution.is_partial,
            "warnings": resolution.warnings,
        }

    def _merge_settings(self, context_data: Dict[str, Any], settings: TimeSettings) -> Dict[str, Any]:
        """Merges system context and organization preferences into the context dictionary."""
        context_data["calendar_type"] = settings.default_calendar
        context_data["financial_year_start_month"] = settings.financial_year_start_month
        context_data["timezone"] = settings.timezone
        context_data["locale"] = settings.locale
        return context_data
