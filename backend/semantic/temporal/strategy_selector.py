from dataclasses import dataclass
from typing import Optional, List
from .enums import TimeStrategyType, StrategySelectionReason
from .models import (
    BaseTimeIntent,
    TimeCapability,
    TimeSettings,
    StrategyCandidate,
)
from .exceptions import StrategyResolutionError
from .strategy_priorities import StrategyPriorityEngine
from .strategy_candidate_generator import StrategyCandidateGenerator


@dataclass
class StrategySelectionResult:
    """The result of selecting a strategy, containing explanation metadata."""
    strategy: TimeStrategyType
    score: int
    reason: StrategySelectionReason


class TimeStrategySelector:
    """
    Coordinates candidate generation and priority engine scoring to choose
    the optimal temporal strategy for a query.
    """
    def __init__(
        self,
        generator: Optional[StrategyCandidateGenerator] = None,
        priority_engine: Optional[StrategyPriorityEngine] = None
    ):
        self.generator = generator or StrategyCandidateGenerator()
        self.priority_engine = priority_engine or StrategyPriorityEngine()

    def select(
        self,
        intent: BaseTimeIntent,
        capability: TimeCapability,
        settings: TimeSettings,
        connection_id: Optional[str] = None
    ) -> StrategySelectionResult:
        
        # Check cache first if connection_id is provided
        if connection_id:
            from .capability_cache import TimeResolutionCache
            cached_entry = TimeResolutionCache.get(connection_id)
            if cached_entry and intent.intent_type in cached_entry.strategy_selections:
                strategy = cached_entry.strategy_selections[intent.intent_type]
                return StrategySelectionResult(
                    strategy=strategy,
                    score=100,
                    reason=StrategySelectionReason.CACHED
                )

        # 1. Generate eligible candidates
        candidates = self.generator.generate(intent, capability, settings)

        # 2. Evaluate candidates using the priority engine to build scored results
        scored_results: List[StrategySelectionResult] = []
        for candidate in candidates:
            score = self.priority_engine.evaluate(candidate, intent, settings)
            scored_results.append(StrategySelectionResult(
                strategy=candidate.strategy,
                score=score,
                reason=candidate.reason
            ))

        if not scored_results:
            raise StrategyResolutionError(
                f"No strategy candidates could be evaluated for intent '{intent.intent_type}' "
                f"on schema capability."
            )

        # 3. Sort scored results to find the highest score
        scored_results.sort(key=lambda r: r.score, reverse=True)
        winner = scored_results[0]

        # Cache winner selection if connection_id is provided
        if connection_id:
            from .capability_cache import TimeResolutionCache
            cached_entry = TimeResolutionCache.get(connection_id)
            if not cached_entry:
                cached_entry = TimeResolutionCache.put(connection_id, capability)
            cached_entry.strategy_selections[intent.intent_type] = winner.strategy
            cached_entry.preferred_strategy = winner.strategy

        return winner
