from typing import Dict, Optional, Any
from .enums import TimeStrategyType, TimeIntentType, CalendarType, StrategySelectionReason
from .models import TimeSettings, BaseTimeIntent

# Default strategy priority scores (magic numbers externalized)
DEFAULT_PRIORITIES: Dict[TimeStrategyType, int] = {
    TimeStrategyType.SNAPSHOT: 100,
    TimeStrategyType.FISCAL: 95,
    TimeStrategyType.CALENDAR_DIMENSION: 85,
    TimeStrategyType.DATE_COLUMN: 70,
    TimeStrategyType.DERIVED: 50,
}


class StrategyPriorityEngine:
    """
    Evaluates and scores StrategyCandidates based on configurable priorities
    and dynamic contextual adjustment rules.
    """
    def __init__(self, priorities: Optional[Dict[TimeStrategyType, int]] = None):
        self.priorities = priorities or DEFAULT_PRIORITIES.copy()

    def get_priority(self, strategy: TimeStrategyType) -> int:
        """Look up the base priority score for a strategy."""
        return self.priorities.get(strategy, 0)

    def evaluate(
        self,
        candidate: Any,  # Avoid circular import by using Any
        intent: BaseTimeIntent,
        settings: TimeSettings
    ) -> int:
        """Calculate score for a candidate strategy based on intent context and settings."""
        base_score = self.get_priority(candidate.strategy)
        
        # Apply contextual rules to adjust/boost scores:
        # Rule 1: Partial snapshot mapping penalty
        if candidate.strategy == TimeStrategyType.SNAPSHOT and candidate.reason == StrategySelectionReason.SNAPSHOT_PARTIAL:
            return 60
            
        # Rule 2: Non-optimal snapshot granularity
        if candidate.strategy == TimeStrategyType.SNAPSHOT and candidate.reason == StrategySelectionReason.SNAPSHOT_NON_OPTIMAL:
            return 20
            
        # Rule 3: Fiscal default calendar boost
        if candidate.strategy == TimeStrategyType.FISCAL and intent.intent_type == TimeIntentType.FISCAL_YTD:
            if settings.default_calendar == CalendarType.FISCAL:
                return 100
            else:
                return 90
                
        # Rule 4: Calendar default boost
        if candidate.strategy == TimeStrategyType.CALENDAR_DIMENSION and intent.intent_type in (TimeIntentType.YTD, TimeIntentType.MTD, TimeIntentType.QTD):
            if settings.default_calendar == CalendarType.CALENDAR:
                return 95
            else:
                return 80
                
        # Rule 5: Date Column optimal for daily/weekly/trends
        from .models import LastNDaysIntent, LastNWeeksIntent
        if candidate.strategy == TimeStrategyType.DATE_COLUMN:
            if isinstance(intent, (LastNDaysIntent, LastNWeeksIntent)) or intent.intent_type in (TimeIntentType.YOY_GROWTH, TimeIntentType.TREND, TimeIntentType.RUNNING_TOTAL):
                return 95

        return base_score
