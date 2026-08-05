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

        # Pipeline execution
        matches, stats = self.pipeline.execute(matching_context)
        self.last_match_stats = stats

        if matches:
            # Remove contained matches first to filter out duplicates/contained sub-phrases
            matches = self._remove_contained_matches(matches)
            # Rank the surviving matches (best candidate first) using the MatchRanker
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
    def _remove_contained_matches(matches: list[MatchResult]) -> list[MatchResult]:
        """
        Remove semantic matches that are fully contained
        inside a longer matched value.
        """
        if len(matches) <= 1:
            return matches

        matches = sorted(
            matches,
            key=lambda m: len(m.normalized_value),
            reverse=True
        )

        filtered = []
        for candidate in matches:
            contained = False
            for kept in filtered:
                if candidate.normalized_value in kept.normalized_value:
                    contained = True
                    break
            if not contained:
                filtered.append(candidate)

        return filtered

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