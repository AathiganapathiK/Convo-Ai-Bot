from typing import List
from .enums import TimeStrategyType, TimeIntentType, StrategySelectionReason
from .models import (
    BaseTimeIntent,
    TimeCapability,
    TimeSettings,
    LastNYearsIntent,
    CurrentYearIntent,
    PreviousYearIntent,
    YearComparisonIntent,
    LastNMonthsIntent,
    PreviousMonthIntent,
    CurrentMonthIntent,
    StrategyCandidate,
)


class StrategyCandidateGenerator:
    """
    Identifies and returns all eligible strategy candidates for a given intent
    based on the database schema capability. Candidates are generated without scores.
    """
    def generate(
        self,
        intent: BaseTimeIntent,
        capability: TimeCapability,
        settings: TimeSettings
    ) -> List[StrategyCandidate]:
        candidates: List[StrategyCandidate] = []

        # 1. Evaluate Snapshot eligibility
        if capability.supports_snapshot_columns:
            is_snapshot_eligible = False
            snapshot_reason = StrategySelectionReason.SNAPSHOT_COLUMNS
            
            if isinstance(intent, (CurrentYearIntent, PreviousYearIntent)):
                is_snapshot_eligible = True
                snapshot_reason = StrategySelectionReason.SNAPSHOT_COLUMNS
            elif isinstance(intent, LastNYearsIntent):
                is_snapshot_eligible = True
                requested = intent.count
                available = len(capability.snapshot_mapping)
                if requested <= available:
                    snapshot_reason = StrategySelectionReason.SNAPSHOT_COLUMNS
                else:
                    snapshot_reason = StrategySelectionReason.SNAPSHOT_PARTIAL
            elif isinstance(intent, YearComparisonIntent):
                is_snapshot_eligible = True
                snapshot_reason = StrategySelectionReason.SNAPSHOT_COLUMNS
            elif isinstance(intent, (CurrentMonthIntent, PreviousMonthIntent, LastNMonthsIntent)):
                is_snapshot_eligible = True
                snapshot_reason = StrategySelectionReason.SNAPSHOT_COLUMNS

            if is_snapshot_eligible:
                candidates.append(StrategyCandidate(
                    strategy=TimeStrategyType.SNAPSHOT,
                    reason=snapshot_reason
                ))
            else:
                candidates.append(StrategyCandidate(
                    strategy=TimeStrategyType.SNAPSHOT,
                    reason=StrategySelectionReason.SNAPSHOT_NON_OPTIMAL
                ))

        # 2. Evaluate Fiscal eligibility
        if capability.supports_fiscal_calendar and intent.intent_type == TimeIntentType.FISCAL_YTD:
            candidates.append(StrategyCandidate(
                strategy=TimeStrategyType.FISCAL,
                reason=StrategySelectionReason.FINANCIAL_YEAR
            ))

        # 3. Evaluate Calendar Dimension eligibility
        if capability.supports_calendar_dimension:
            candidates.append(StrategyCandidate(
                strategy=TimeStrategyType.CALENDAR_DIMENSION,
                reason=StrategySelectionReason.CALENDAR_TABLE
            ))

        # 4. Evaluate Date Column eligibility
        if capability.supports_date_columns:
            candidates.append(StrategyCandidate(
                strategy=TimeStrategyType.DATE_COLUMN,
                reason=StrategySelectionReason.DATE_COLUMNS
            ))

        return candidates
