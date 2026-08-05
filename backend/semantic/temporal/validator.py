import datetime
from .models import (
    BaseTimeIntent,
    LastNDaysIntent,
    LastNWeeksIntent,
    LastNMonthsIntent,
    LastNYearsIntent,
    DateRangeIntent,
    YearRangeIntent,
    MonthRangeIntent,
    YearComparisonIntent,
    MonthComparisonIntent,
    GrowthIntent,
    TimeValidationResult,
)


class TimeIntentValidator:
    """
    Validates model constraints on time intelligence intents.
    """

    @staticmethod
    def validate(intent: BaseTimeIntent) -> TimeValidationResult:
        """
        Validates the state of a temporal intent.
        Returns a TimeValidationResult.
        """
        errors = []
        warnings = []

        if not isinstance(intent, BaseTimeIntent):
            errors.append("Object is not a valid TimeIntent instance.")
            return TimeValidationResult(passed=False, errors=errors, warnings=warnings)

        # Last N validation
        if isinstance(intent, (LastNDaysIntent, LastNWeeksIntent, LastNMonthsIntent, LastNYearsIntent)):
            if intent.count <= 0:
                errors.append(f"Count must be greater than 0, got {intent.count}.")

        # Date Range validation
        elif isinstance(intent, DateRangeIntent):
            if intent.start_date is None or intent.end_date is None:
                errors.append("DateRangeIntent must specify both start_date and end_date.")
            elif intent.start_date > intent.end_date:
                errors.append(
                    f"Start date ({intent.start_date}) cannot be after end date ({intent.end_date})."
                )

        # Year Range validation
        elif isinstance(intent, YearRangeIntent):
            if intent.start_year > intent.end_year:
                errors.append(
                    f"Start year ({intent.start_year}) cannot be after end year ({intent.end_year})."
                )

        # Month Range validation
        elif isinstance(intent, MonthRangeIntent):
            if not (1 <= intent.start_month <= 12) or not (1 <= intent.end_month <= 12):
                errors.append("Months must be between 1 and 12.")
            if intent.start_year > intent.end_year:
                errors.append(
                    f"Start year ({intent.start_year}) cannot be after end year ({intent.end_year})."
                )
            if intent.start_year == intent.end_year and intent.start_month > intent.end_month:
                errors.append(
                    f"Start month ({intent.start_month}) cannot be after end month ({intent.end_month}) in the same year."
                )

        # Year Comparison validation
        elif isinstance(intent, YearComparisonIntent):
            if intent.start_year > intent.end_year:
                errors.append(
                    f"Start year ({intent.start_year}) cannot be after end year ({intent.end_year})."
                )

        # Month Comparison validation
        elif isinstance(intent, MonthComparisonIntent):
            if not (1 <= intent.start_month <= 12) or not (1 <= intent.end_month <= 12):
                errors.append("Months must be between 1 and 12.")
            if intent.start_year > intent.end_year:
                errors.append(
                    f"Start year ({intent.start_year}) cannot be after end year ({intent.end_year})."
                )
            if intent.start_year == intent.end_year and intent.start_month > intent.end_month:
                errors.append(
                    f"Start month ({intent.start_month}) cannot be after end month ({intent.end_month}) in the same year."
                )

        return TimeValidationResult(
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
