from dataclasses import dataclass
from sqlalchemy import text
import re
from database import engine

from semantic.matching import (
    MatchType,
    MatchResult,
    QuestionContext,
    CachedDimensionValue,
    MatchingContext,
    MatchingPipeline,
    MatchRanker,
    ExactMatcher,
    NormalizedMatcher,
    SingularPluralMatcher,
    FuzzyMatcher,
    STOPWORDS,
    QuestionSanitizer
)
from semantic.cache import DimensionValueCache


@dataclass
class ResolvedDimensionValue:
    original_value: str
    resolved_value: str
    confidence: float
    match_type: MatchType
    column_name: str


class DimensionValueResolver:
    """
    Resolves business values mentioned in a user's question
    using the semantic dimension value index.
    """
    
    default_cache = DimensionValueCache()
    last_match_stats = None

    def __init__(self, pipeline: MatchingPipeline = None, cache: DimensionValueCache = None, settings: dict = None):
        self.cache = cache or self.default_cache
        self.settings = settings or {}
        if pipeline is None:
            # Composer: Resolver instantiates matchers and injects them into the pipeline
            default_matchers = [
                ExactMatcher(),
                NormalizedMatcher(),
                SingularPluralMatcher(),
                FuzzyMatcher()
            ]
            self.pipeline = MatchingPipeline(matchers=default_matchers)
        else:
            self.pipeline = pipeline
        self.last_match_stats = None

    @classmethod
    def clear_cache(cls, connection_id: str = None):
        """
        Clears the cached preprocessed dimension values in the default cache.
        """
        if connection_id:
            cls.default_cache.invalidate(connection_id)
        else:
            cls.default_cache.clear()

    def invalidate_cache(self, connection_id: str = None):
        """
        Clears/invalidates cached entries in the active cache instance.
        """
        if connection_id:
            self.cache.invalidate(connection_id)
        else:
            self.cache.clear()

    @classmethod
    def resolve(
        cls,
        connection_id: str,
        question: str
    ):
        """
        Backward-compatible static entry point.
        """
        resolver = cls()
        results = resolver.resolve_matches(connection_id, question)
        cls.last_match_stats = resolver.last_match_stats
        return results

    def resolve_matches(
        self,
        connection_id: str,
        question: str
    ):
        """
        Resolve matches using the injected matching pipeline.
        """

        question = QuestionSanitizer.sanitize(question)
        normalized_question = self._normalize_text(question)
        
        # 1) Pre-compute question tokens (excluding stopwords) and singulars once
        q_tokens = [t for t in normalized_question.split() if t not in STOPWORDS]
        q_singulars = [SingularPluralMatcher._to_singular(t) for t in q_tokens]

        question_context = QuestionContext(
            raw_question=question,
            normalized_question=normalized_question,
            q_tokens=q_tokens,
            q_singulars=q_singulars
        )

        indexed_values = self._load_dimension_values(connection_id)

        matching_context = MatchingContext(
            question_context=question_context,
            connection_id=connection_id,
            indexed_values=indexed_values,
            settings=self.settings
        )
        
        matches, stats = self.pipeline.execute(matching_context)
        self.last_match_stats = stats

        if matches:
            # Step 1:
            # Different matchers may return the same indexed value.
            # Consolidate those duplicate pieces of evidence first.
            matches = self._consolidate_duplicate_matches(matches)

            # Step 2:
            # Remove genuinely contained candidate values.
            matches = self._remove_contained_matches(matches, q_tokens)

            # Step 3:
            # Rank the remaining candidates globally.
            matches = MatchRanker.rank(matches, q_tokens)

            # Map back to dicts for backward compatibility across downstream components (e.g. PromptBuilder)
            return [
                {
                    "dimension_id": m.dimension_id,
                    "business_name": m.business_name,
                    "table_name": m.table_name,
                    "column_name": m.column_name,
                    "value": m.value,
                    "normalized_value": m.normalized_value,
                    "confidence": m.confidence,
                    "match_type": m.match_type.value,
                    "matched_question_tokens": m.matched_question_tokens,
                    "matched_value_tokens": m.matched_value_tokens,
                    "reason": m.reason
                }
                for m in matches
            ]

        return []

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize text for semantic matching:
        - lowercase
        - trim
        - remove apostrophes
        - replace delimiters (-, _, /, .) with spaces
        - collapse multiple spaces
        """
        if text is None:
            return ""
        text = text.lower().strip()
        # Remove apostrophes
        text = text.replace("'", "")
        # Replace delimiters with spaces
        text = re.sub(r"[-_/.]", " ", text)
        # Collapse multiple spaces
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _normalize_question(question: str) -> str:
        """
        Backward-compatible helper redirecting to _normalize_text.
        """
        return DimensionValueResolver._normalize_text(question)

    def _load_dimension_values(self, connection_id: str) -> list[CachedDimensionValue]:
        """
        Load all indexed semantic values for a connection.
        Utilizes version-aware cache if available.
        """
        cached = self.cache.get(connection_id)
        if cached is not None:
            return cached

        query = text("""
            SELECT
                dvi.semantic_dimension_id,
                sd.business_name,
                sd.table_name,
                sd.column_name,
                dvi.value,
                dvi.normalized_value
            FROM dimension_value_index dvi
            INNER JOIN semantic_dimensions sd 
                ON sd.dimension_id = dvi.semantic_dimension_id
            WHERE
                dvi.connection_id = :connection_id
                AND sd.is_active = 1
            ORDER BY
                sd.business_name,
                dvi.value
        """)

        with engine.connect() as conn:
            result = conn.execute(
                query,
                {"connection_id": connection_id}
            )
            rows = [dict(row._mapping) for row in result.fetchall()]

        cached_values = []
        for row in rows:
            raw_value = row["value"]
            stored_normalized = row["normalized_value"]
            if not raw_value:
                continue

            norm_val_raw = self._normalize_text(raw_value)
            val_tokens = [t for t in norm_val_raw.split() if t not in STOPWORDS]
            val_singulars = [SingularPluralMatcher._to_singular(t) for t in val_tokens]

            norm_val_stored = self._normalize_text(stored_normalized) if stored_normalized else ""
            stored_tokens = [t for t in norm_val_stored.split() if t not in STOPWORDS]
            stored_singulars = [SingularPluralMatcher._to_singular(t) for t in stored_tokens]

            cached_values.append(CachedDimensionValue(
                semantic_dimension_id=row["semantic_dimension_id"],
                business_name=row["business_name"],
                table_name=row["table_name"],
                column_name=row["column_name"],
                value=raw_value,
                normalized_value=stored_normalized if stored_normalized else "",
                runtime_stored_norm=norm_val_stored,
                runtime_stored_tokens=stored_tokens,
                runtime_stored_singulars=stored_singulars,
                runtime_raw_norm=norm_val_raw,
                runtime_raw_tokens=val_tokens,
                runtime_raw_singulars=val_singulars
            ))

        self.cache.put(connection_id, cached_values)
        return cached_values

    @staticmethod
    def _rank_matches(matches: list[MatchResult], question_tokens: list) -> list[MatchResult]:
        """
        Backward-compatible helper redirecting to MatchRanker.rank.
        """
        return MatchRanker.rank(matches, question_tokens)

    @staticmethod
    def _is_contiguous_sublist(sublist: list, main_list: list) -> bool:
        if not sublist:
            return True
        sub_len = len(sublist)
        for i in range(len(main_list) - sub_len + 1):
            if main_list[i : i + sub_len] == sublist:
                return True
        return False

    @staticmethod
    def _find_matched_question_span(v_tokens: list[str], q_tokens: list[str]) -> list[str]:
        if not v_tokens or not q_tokens:
            return []
        
        q_sing = [SingularPluralMatcher._to_singular(t) for t in q_tokens]
        v_sing = [SingularPluralMatcher._to_singular(t) for t in v_tokens]
        
        # 1) Try exact contiguous singularized match first
        v_len = len(v_sing)
        for i in range(len(q_sing) - v_len + 1):
            if q_sing[i : i + v_len] == v_sing:
                return q_tokens[i : i + v_len]
        
        # 2) Longest contiguous sublist of q_sing that matches a contiguous sublist of v_sing
        for width in range(len(q_sing), 0, -1):
            for i in range(len(q_sing) - width + 1):
                sub = q_sing[i : i + width]
                if DimensionValueResolver._is_contiguous_sublist(sub, v_sing):
                    return q_tokens[i : i + width]
                    
        return []

    @staticmethod
    def _remove_contained_matches(matches: list[MatchResult], q_tokens: list[str]) -> list[MatchResult]:
        """
        Remove semantic matches that are fully contained
        inside a longer matched value.
        """
        if len(matches) <= 1:
            return matches

        # Sort matches by the length of their matched question span descending,
        # keeping direct matches before fuzzy matches if span lengths are equal.
        def sort_key(m):
            span = DimensionValueResolver._find_matched_question_span(m.matched_value_tokens, q_tokens)
            is_direct = m.match_type in (MatchType.EXACT, MatchType.NORMALIZED, MatchType.SINGULAR_PLURAL)
            return (len(span), 1 if is_direct else 0, len(m.normalized_value))

        matches = sorted(matches, key=sort_key, reverse=True)

        filtered = []
        for candidate in matches:
            candidate_span = DimensionValueResolver._find_matched_question_span(candidate.matched_value_tokens, q_tokens)
            
            # Discard FUZZY candidates whose matching tokens are split non-contiguously in the question
            if candidate.match_type == MatchType.FUZZY:
                q_sing = [SingularPluralMatcher._to_singular(t) for t in q_tokens]
                v_sing = [SingularPluralMatcher._to_singular(t) for t in candidate.matched_value_tokens]
                present_tokens = {t for t in v_sing if t in q_sing}
                candidate_span_sing = {SingularPluralMatcher._to_singular(t) for t in candidate_span}
                if len(present_tokens) > len(candidate_span_sing):
                    continue

            suppressed = False
            for kept in filtered:
                kept_span = DimensionValueResolver._find_matched_question_span(kept.matched_value_tokens, q_tokens)
                
                # Rule 1: Direct match suppresses fuzzy match on the same question span
                if (candidate.match_type == MatchType.FUZZY and 
                    kept.match_type in (MatchType.EXACT, MatchType.NORMALIZED, MatchType.SINGULAR_PLURAL) and 
                    candidate_span == kept_span and len(candidate_span) > 0):
                    suppressed = True
                    break
                
                # Rule 2: Strict contiguous sublist containment
                if (len(candidate_span) < len(kept_span) and 
                    len(candidate_span) > 0 and
                    DimensionValueResolver._is_contiguous_sublist(candidate_span, kept_span)):
                    suppressed = True
                    break
                    
            if not suppressed:
                filtered.append(candidate)

        return filtered


    @staticmethod
    def _consolidate_duplicate_matches(
        matches: list[MatchResult],
    ) -> list[MatchResult]:
        """
        Consolidate multiple matcher results that refer to the same
        indexed semantic dimension value.

        Different matchers may independently discover the same value.
        For example:

            ExactMatcher      -> T-Shirt
            NormalizedMatcher -> T-Shirt

        These are different pieces of matching evidence for the same
        semantic value and must become one candidate.

        The strongest candidate is retained using the following
        deterministic priority:

            EXACT             > NORMALIZED
            > SINGULAR_PLURAL > FUZZY

        If the match type is identical, higher confidence wins.
        If confidence is also identical, the candidate with greater
        question-token coverage wins.
        If all of those are equal, the first candidate is retained.

        Candidates representing different indexed values are never
        consolidated here.
        """

        if len(matches) <= 1:
            return matches

        match_type_priority = {
            MatchType.EXACT: 4,
            MatchType.NORMALIZED: 3,
            MatchType.SINGULAR_PLURAL: 2,
            MatchType.FUZZY: 1,
        }

        consolidated: dict[tuple, MatchResult] = {}

        for candidate in matches:
            identity = (
                candidate.dimension_id,
                candidate.normalized_value.strip().lower(),
            )

            existing = consolidated.get(identity)

            if existing is None:
                consolidated[identity] = candidate
                continue

            existing_priority = match_type_priority.get(
                existing.match_type,
                0,
            )

            candidate_priority = match_type_priority.get(
                candidate.match_type,
                0,
            )

            if candidate_priority > existing_priority:
                consolidated[identity] = candidate
                continue

            if candidate_priority < existing_priority:
                continue

            existing_coverage = len(
                existing.matched_question_tokens or []
            )

            candidate_coverage = len(
                candidate.matched_question_tokens or []
            )

            if candidate.confidence > existing.confidence:
                consolidated[identity] = candidate
                continue

            if (
                candidate.confidence == existing.confidence
                and candidate_coverage > existing_coverage
            ):
                consolidated[identity] = candidate

        return list(consolidated.values())

    @staticmethod
    def _filter_metric_conflicts(
        value_matches: list,
        metric_objects: list
    ) -> list:
        """
        Remove dimension value matches that duplicate already
        resolved metrics.
        """
        metric_names = set()
        for metric in metric_objects:
            if metric.get("metric_name"):
                metric_names.add(metric["metric_name"].lower())
            if metric.get("business_name"):
                metric_names.add(metric["business_name"].lower())

        return [
            match
            for match in value_matches
            if match["normalized_value"] not in metric_names
        ]