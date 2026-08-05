import time
from typing import List, Tuple
from semantic.matching.models import MatchingContext, MatchResult, MatchStatistics, BaseMatcher, MatchType

class MatchingPipeline:
    def __init__(self, matchers: List[BaseMatcher]):
        if matchers is None:
            raise ValueError("MatchingPipeline requires a list of matchers.")
        self.matchers = matchers
        
    def execute(self, context: MatchingContext) -> Tuple[List[MatchResult], MatchStatistics]:
        """
        Executes each matcher sequentially.
        """
        exact_attempted = False
        normalized_attempted = False
        plural_attempted = False
        fuzzy_attempted = False
        winning_match = None
        
        start_time = time.perf_counter()
        matches = []
        
        for matcher in self.matchers:
            m_type = getattr(matcher, "match_type", None)
            if m_type == MatchType.EXACT:
                exact_attempted = True
            elif m_type == MatchType.NORMALIZED:
                normalized_attempted = True
            elif m_type == MatchType.SINGULAR_PLURAL:
                plural_attempted = True
            elif m_type == MatchType.FUZZY:
                fuzzy_attempted = True
                
            res = matcher.match(context)
            if res:
                matches = res
                winning_match = matcher.__class__.__name__
                break
                
        execution_time_ms = (time.perf_counter() - start_time) * 1000.0
        
        stats = MatchStatistics(
            exact_attempted=exact_attempted,
            normalized_attempted=normalized_attempted,
            plural_attempted=plural_attempted,
            fuzzy_attempted=fuzzy_attempted,
            winning_match=winning_match,
            execution_time_ms=execution_time_ms
        )
        
        return matches, stats
