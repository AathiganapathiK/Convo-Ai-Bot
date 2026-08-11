import time
from typing import List, Tuple

from semantic.matching.models import (
    MatchingContext,
    MatchResult,
    MatchStatistics,
    BaseMatcher,
    MatchType,
)


class MatchingPipeline:
    def __init__(self, matchers: List[BaseMatcher]):
        if matchers is None:
            raise ValueError("MatchingPipeline requires a list of matchers.")

        self.matchers = matchers

    def execute(
        self,
        context: MatchingContext,
    ) -> Tuple[List[MatchResult], MatchStatistics]:
        """
        Execute every configured matcher and collect all candidate matches.

        The pipeline is responsible only for matcher orchestration.

        It intentionally does NOT:
        - rank candidates
        - remove duplicate candidates
        - remove contained matches
        - select a final winner

        Those responsibilities remain downstream in
        DimensionValueResolver.
        """

        exact_attempted = False
        normalized_attempted = False
        plural_attempted = False
        fuzzy_attempted = False

        exact_match_count = 0
        normalized_match_count = 0
        plural_match_count = 0
        fuzzy_match_count = 0

        all_matches: List[MatchResult] = []

        start_time = time.perf_counter()

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

            # IMPORTANT:
            # Every configured matcher must execute.
            #
            # The old implementation stopped here when a matcher
            # returned a result. That caused later matchers to be
            # skipped and produced incomplete candidate coverage.
            res = matcher.match(context)

            if not res:
                continue

            # Preserve every candidate returned by this matcher.
            #
            # Do not deduplicate or rank here. Those responsibilities
            # remain in DimensionValueResolver.
            all_matches.extend(res)

            result_count = len(res)

            if m_type == MatchType.EXACT:
                exact_match_count += result_count

            elif m_type == MatchType.NORMALIZED:
                normalized_match_count += result_count

            elif m_type == MatchType.SINGULAR_PLURAL:
                plural_match_count += result_count

            elif m_type == MatchType.FUZZY:
                fuzzy_match_count += result_count

        execution_time_ms = (
            time.perf_counter() - start_time
        ) * 1000.0

        stats = MatchStatistics(
            exact_attempted=exact_attempted,
            normalized_attempted=normalized_attempted,
            plural_attempted=plural_attempted,
            fuzzy_attempted=fuzzy_attempted,

            # There is intentionally no pipeline-level winner anymore.
            # MatchRanker determines final candidate ordering downstream.
            winning_match=None,

            execution_time_ms=execution_time_ms,

            exact_match_count=exact_match_count,
            normalized_match_count=normalized_match_count,
            plural_match_count=plural_match_count,
            fuzzy_match_count=fuzzy_match_count,
            total_match_count=len(all_matches),
        )

        return all_matches, stats