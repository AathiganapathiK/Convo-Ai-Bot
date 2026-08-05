import datetime
from typing import Optional, Any, Union

from .models import (
    BaseTimeIntent,
    TimeCapability,
    TimeSettings,
    TimeResolutionResult,
    ResolvedTimePlan,
)
from .enums import TimeStrategyType
from .detector import TemporalDetector
from .strategy_selector import TimeStrategySelector
from .resolver import TimeStrategyResolver


class TimeResolver:
    """
    Unified public API / orchestrator for the Temporal Intelligence Engine.
    Resolves raw user questions or structured intents into complete temporal plans.
    """
    def __init__(
        self,
        detector: Optional[TemporalDetector] = None,
        selector: Optional[TimeStrategySelector] = None,
        strategy_resolver: Optional[TimeStrategyResolver] = None
    ):
        self.detector = detector or TemporalDetector()
        self.selector = selector or TimeStrategySelector()
        self.strategy_resolver = strategy_resolver or TimeStrategyResolver()

    def resolve(
        self,
        question: str,
        capability: Optional[TimeCapability] = None,
        settings: Optional[TimeSettings] = None,
        connection_id: Optional[str] = None,
        reference_date: Optional[datetime.date] = None
    ) -> TimeResolutionResult:
        """
        Detects the intent from a raw natural language question, selects the strategy,
        executes the strategy, and returns a unified TimeResolutionResult.
        """
        ref_date = reference_date or datetime.date.today()
        
        # 1. Input normalization: run detector on the question
        intent = self.detector.detect(question, reference_date=ref_date)
        if not intent:
            return TimeResolutionResult(
                resolved=False,
                warnings=["Could not detect any temporal intent from the question."],
                confidence=0.0
            )

        # 2. Call resolve_intent to perform strategy selection and execution
        return self.resolve_intent(
            intent=intent,
            capability=capability,
            settings=settings,
            connection_id=connection_id,
            confidence=1.0  # Default detection confidence
        )

    def resolve_intent(
        self,
        intent: BaseTimeIntent,
        capability: Optional[TimeCapability] = None,
        settings: Optional[TimeSettings] = None,
        connection_id: Optional[str] = None,
        confidence: float = 1.0
    ) -> TimeResolutionResult:
        """
        Resolves an already detected intent by selecting and executing the strategy.
        """
        active_settings = settings or TimeSettings()
        active_capability = capability or TimeCapability()

        # If capability was not provided but connection_id is, try to load it from cache
        if capability is None and connection_id:
            from .capability_cache import TimeResolutionCache
            cached_entry = TimeResolutionCache.get(connection_id)
            if cached_entry:
                active_capability = cached_entry.capability

        try:
            # 2. Strategy selection
            selection_result = self.selector.select(
                intent=intent,
                capability=active_capability,
                settings=active_settings,
                connection_id=connection_id
            )

            # 3. Strategy execution
            plan = self.strategy_resolver.resolve(
                intent=intent,
                capability=active_capability,
                settings=active_settings,
                connection_id=connection_id,
                strategy=selection_result.strategy
            )

            # 4. Final assembly
            return TimeResolutionResult(
                resolved=True,
                intent=intent,
                plan=plan,
                warnings=plan.warnings,
                is_partial=plan.is_partial,
                confidence=confidence,
                selection_reason=selection_result.reason,
                selection_score=selection_result.score
            )

        except Exception as e:
            return TimeResolutionResult(
                resolved=False,
                intent=intent,
                warnings=[f"Failed to resolve strategy: {str(e)}"],
                confidence=confidence
            )
