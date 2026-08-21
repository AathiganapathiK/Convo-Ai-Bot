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
    QuestionSanitizer,
    ResolutionStatus,
    AmbiguityChoice,
    SemanticResolutionResult,
    AmbiguityClassifier
)
from semantic.cache import DimensionValueCache


@dataclass
class ResolvedDimensionValue:
    original_value: str
    resolved_value: str
    confidence: float
    match_type: MatchType
    column_name: str


import threading

class ResolutionResultList(list):
    """
    A list subclass that holds request-local resolution metadata.
    """
    def __init__(self, iterable, resolution_result=None, followup_context=None, match_stats=None):
        super().__init__(iterable)
        self.resolution_result = resolution_result
        self.followup_context = followup_context
        self.match_stats = match_stats


class ThreadLocalMeta(type):
    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        cls._local = threading.local()

    @property
    def last_match_stats(cls):
        return getattr(cls._local, 'last_match_stats', None)

    @last_match_stats.setter
    def last_match_stats(cls, value):
        cls._local.last_match_stats = value

    @property
    def last_resolution_result(cls):
        return getattr(cls._local, 'last_resolution_result', None)

    @last_resolution_result.setter
    def last_resolution_result(cls, value):
        cls._local.last_resolution_result = value

    @property
    def last_followup_context(cls):
        return getattr(cls._local, 'last_followup_context', None)

    @last_followup_context.setter
    def last_followup_context(cls, value):
        cls._local.last_followup_context = value


class DimensionValueResolver(metaclass=ThreadLocalMeta):
    """
    Resolves business values mentioned in a user's question
    using the semantic dimension value index.
    """
    
    default_cache = DimensionValueCache()

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
        self.last_resolution_result = None
        self.followup_context = None

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
        question: str,
        clarified_candidate: dict = None,
        dimension_context: list = None,
        previous_semantic_context: dict = None,
        current_metrics: list = None,
        all_metrics: list = None,
        all_dimensions: list = None
    ):
        """
        Backward-compatible static entry point.
        """
        resolver = cls()
        results = resolver.resolve_matches(
            connection_id,
            question,
            clarified_candidate,
            dimension_context,
            previous_semantic_context,
            current_metrics,
            all_metrics,
            all_dimensions
        )
        cls.last_match_stats = resolver.last_match_stats
        cls.last_resolution_result = resolver.last_resolution_result
        cls.last_followup_context = getattr(resolver, "followup_context", None)
        return results

    def resolve_matches(
        self,
        connection_id: str,
        question: str,
        clarified_candidate: dict = None,
        dimension_context: list = None,
        previous_semantic_context: dict = None,
        current_metrics: list = None,
        all_metrics: list = None,
        all_dimensions: list = None
    ):

        """
        Resolve matches using the injected matching pipeline.
        """
        if clarified_candidate:
            from semantic.matching.models import MatchResult, MatchType, AmbiguityChoice, ResolutionStatus, SemanticResolutionResult
            m = MatchResult(
                matched=True,
                value=clarified_candidate["value"],
                normalized_value=clarified_candidate.get("normalized_value", clarified_candidate["value"].lower()),
                confidence=clarified_candidate.get("confidence", 1.0),
                match_type=MatchType(clarified_candidate.get("match_type", "EXACT")),
                matched_question_tokens=clarified_candidate.get("matched_question_tokens", []),
                matched_value_tokens=clarified_candidate.get("matched_value_tokens", []),
                reason="Clarified by user",
                dimension_id=clarified_candidate.get("dimension_id"),
                business_name=clarified_candidate.get("business_name"),
                table_name=clarified_candidate.get("table_name"),
                column_name=clarified_candidate.get("column_name")
            )
            choice = AmbiguityChoice(
                result=m,
                actual_query_coverage=len(m.matched_question_tokens),
                matched_query_tokens=m.matched_question_tokens
            )
            self.last_resolution_result = SemanticResolutionResult(
                status=ResolutionStatus.SINGLE_MATCH,
                candidates=[choice],
                dominant_match=choice
            )
            return ResolutionResultList(
                [
                    {
                        "dimension_id": m.dimension_id,
                        "business_name": m.business_name,
                        "table_name": m.table_name,
                        "column_name": m.column_name,
                        "value": m.value,
                        "normalized_value": m.normalized_value,
                        "confidence": m.confidence,
                        "match_type": m.match_type.value,
                        "matched_question_tokens": choice.matched_query_tokens,
                        "matched_value_tokens": m.matched_value_tokens,
                        "reason": m.reason
                    }
                ],
                resolution_result=self.last_resolution_result,
                followup_context=getattr(self, "followup_context", None),
                match_stats=self.last_match_stats
            )


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

            # Apply explicit dimension context filtering if dimension_context is provided
            has_explicit_label = False
            if dimension_context:
                q_words = normalized_question.split()
                filtered_matches = []
                for m in matches:
                    val_norm = m.normalized_value or m.value.lower()
                    indices = self._find_match_span_indices(q_words, val_norm)
                    explicit_dim = None
                    if indices:
                        min_idx = min(indices)
                        max_idx = max(indices)
                        adjacent_words = []
                        if min_idx > 0:
                            adjacent_words.append(q_words[min_idx - 1])
                        if max_idx < len(q_words) - 1:
                            adjacent_words.append(q_words[max_idx + 1])
                        for word in adjacent_words:
                            matched_dim_name = self._find_matching_dimension(word, dimension_context)
                            if matched_dim_name:
                                explicit_dim = matched_dim_name
                                break
                    if explicit_dim:
                        has_explicit_label = True
                        cand_dim_name = m.business_name or m.column_name or ""
                        if cand_dim_name.lower() == explicit_dim.lower():
                            filtered_matches.append(m)
                    else:
                        filtered_matches.append(m)
                matches = filtered_matches

            # Initialize followup_context debug structure
            self.followup_context = {
                "applied": False,
                "reason": "NO_ELIGIBLE_PREVIOUS_CONTEXT"
            }

            # Check eligibility for follow-up dimension inheritance
            if previous_semantic_context and matches:
                # 1. Check if the current query has a single target semantic value
                distinct_values = {m.normalized_value or m.value.lower() for m in matches}
                is_single_target = len(distinct_values) == 1

                # 2. Check if that value has candidates belonging to multiple dimensions
                has_multiple_dims = len(set(m.dimension_id for m in matches if m.dimension_id is not None)) > 1 or len(set(m.business_name for m in matches if m.business_name is not None)) > 1

                is_metric_shift = False
                if current_metrics and len(current_metrics) > 0:
                    prev_metrics_set = set()
                    for pm in previous_semantic_context.get("metrics", []):
                        if pm.get("business_name"):
                            prev_metrics_set.add(pm["business_name"].strip().lower())
                        if pm.get("metric_name"):
                            prev_metrics_set.add(pm["metric_name"].strip().lower())

                    current_metrics_set = set()
                    for cm in current_metrics:
                        if cm.get("business_name"):
                            current_metrics_set.add(cm["business_name"].strip().lower())
                        if cm.get("metric_name"):
                            current_metrics_set.add(cm["metric_name"].strip().lower())

                    if not (current_metrics_set and current_metrics_set.issubset(prev_metrics_set)):
                        is_metric_shift = True

                if has_explicit_label:
                    self.followup_context = {
                        "applied": False,
                        "reason": "EXPLICIT_DIMENSION_LABEL_PRESENT"
                    }
                elif not is_single_target:
                    self.followup_context = {
                        "applied": False,
                        "reason": "MULTIPLE_TARGET_VALUES"
                    }
                elif not has_multiple_dims:
                    self.followup_context = {
                        "applied": False,
                        "reason": "SINGLE_DIMENSION_VALUE"
                    }
                elif is_metric_shift:
                    self.followup_context = {
                        "applied": False,
                        "reason": "CURRENT_METRICS_PRESENT"
                    }
                else:
                    # 4. Extract previous turn's successfully resolved dimensions and metrics
                    prev_resolved_values = previous_semantic_context.get("resolved_values", [])
                    prev_dimensions = previous_semantic_context.get("dimensions", [])

                    prev_dims_set = set()
                    for rv in prev_resolved_values:
                        if rv.get("business_name"):
                            prev_dims_set.add(rv["business_name"].lower())
                        if rv.get("dimension_name"):
                            prev_dims_set.add(rv["dimension_name"].lower())
                    for d in prev_dimensions:
                        if d.get("business_name"):
                            prev_dims_set.add(d["business_name"].lower())
                        if d.get("dimension_name"):
                            prev_dims_set.add(d["dimension_name"].lower())

                    # Determine if previous turn successfully resolved a concrete dimension
                    if not prev_dims_set:
                        self.followup_context = {
                            "applied": False,
                            "reason": "NO_PREVIOUS_RESOLVED_DIMENSION"
                        }
                    else:
                        # Find candidates matching the previous dimension
                        matching_candidates = []
                        for m in matches:
                            cand_dim_names = {
                                (m.business_name or "").lower(),
                                (m.column_name or "").lower()
                            }
                            if cand_dim_names & prev_dims_set:
                                matching_candidates.append(m)

                        if not matching_candidates:
                            self.followup_context = {
                                "applied": False,
                                "reason": "NO_CANDIDATE_MATCHING_PREVIOUS_DIMENSION"
                            }
                        else:
                            # Inherit the previous dimension context!
                            matches = matching_candidates
                            
                            # Find the first previous resolved value/dimension details for debugging
                            prev_dim_lower = next(iter(prev_dims_set))
                            prev_dim = prev_dim_lower
                            prev_val_str = ""
                            found = False
                            for rv in prev_resolved_values:
                                name = rv.get("business_name") or rv.get("dimension_name") or ""
                                if name.lower() == prev_dim_lower:
                                    prev_dim = name
                                    prev_val_str = rv.get("value", "")
                                    found = True
                                    break
                            if not found:
                                for d in prev_dimensions:
                                    name = d.get("business_name") or d.get("dimension_name") or ""
                                    if name.lower() == prev_dim_lower:
                                        prev_dim = name
                                        found = True
                                        break
                            
                            self.followup_context = {
                                "applied": True,
                                "previous_dimension": prev_dim,
                                "previous_value": prev_val_str,
                                "current_value": next(iter(distinct_values)),
                                "reason": "PREVIOUS_DIMENSION_MATCH"
                            }
            else:
                self.followup_context = {
                    "applied": False,
                    "reason": "NO_ELIGIBLE_PREVIOUS_CONTEXT"
                }

            # Step 3:
            # Rank the remaining candidates globally.
            matches = MatchRanker.rank(matches, q_tokens)

            self.last_resolution_result = AmbiguityClassifier.classify(
                matches,
                q_tokens,
                connection_id=connection_id,
                indexed_values=indexed_values,
                dimension_context=dimension_context,
                current_metrics=current_metrics,
                all_metrics=all_metrics,
                all_dimensions=all_dimensions
            )


            # Map back to dicts for backward compatibility across downstream components (e.g. PromptBuilder)
            # If there is a dominant match (e.g. in SINGLE_MATCH or WEAK_AMBIGUITY), only return that match
            # to avoid cross-talk pollution when SQL generation is allowed.
            if self.last_resolution_result.dominant_match:
                dom_choice = self.last_resolution_result.dominant_match
                m = dom_choice.result
                return ResolutionResultList(
                    [
                        {
                            "dimension_id": m.dimension_id,
                            "business_name": m.business_name,
                            "table_name": m.table_name,
                            "column_name": m.column_name,
                            "value": m.value,
                            "normalized_value": m.normalized_value,
                            "confidence": m.confidence,
                            "match_type": m.match_type.value,
                            # Use clean matched_query_tokens from classifier to avoid pollution
                            "matched_question_tokens": dom_choice.matched_query_tokens,
                            "matched_value_tokens": m.matched_value_tokens,
                            "reason": m.reason
                        }
                    ],
                    resolution_result=self.last_resolution_result,
                    followup_context=getattr(self, "followup_context", None),
                    match_stats=self.last_match_stats
                )

            # Otherwise (e.g. STRONG_AMBIGUITY), return all candidates with clean matched_question_tokens
            # so they are returned in semantic_result for the UI/clarification.
            return ResolutionResultList(
                [
                    {
                        "dimension_id": choice.result.dimension_id,
                        "business_name": choice.result.business_name,
                        "table_name": choice.result.table_name,
                        "column_name": choice.result.column_name,
                        "value": choice.result.value,
                        "normalized_value": choice.result.normalized_value,
                        "confidence": choice.result.confidence,
                        "match_type": choice.result.match_type.value,
                        "matched_question_tokens": choice.matched_query_tokens,
                        "matched_value_tokens": choice.result.matched_value_tokens,
                        "reason": choice.result.reason
                    }
                    for choice in self.last_resolution_result.candidates
                ],
                resolution_result=self.last_resolution_result,
                followup_context=getattr(self, "followup_context", None),
                match_stats=self.last_match_stats
            )

        self.last_resolution_result = AmbiguityClassifier.classify([])
        return ResolutionResultList(
            [],
            resolution_result=self.last_resolution_result,
            followup_context=getattr(self, "followup_context", None),
            match_stats=self.last_match_stats
        )

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

        def get_span(m):
            if m.match_type == MatchType.FUZZY and m.matched_question_tokens:
                return m.matched_question_tokens
            return DimensionValueResolver._find_matched_question_span(m.matched_value_tokens, q_tokens)

        # Sort matches by the length of their matched question span descending,
        # keeping direct matches before fuzzy matches if span lengths are equal.
        def sort_key(m):
            span = get_span(m)
            is_direct = m.match_type in (MatchType.EXACT, MatchType.NORMALIZED, MatchType.SINGULAR_PLURAL)
            return (len(span), 1 if is_direct else 0, len(m.normalized_value))

        matches = sorted(matches, key=sort_key, reverse=True)

        filtered = []
        for candidate in matches:
            candidate_span = get_span(candidate)
            
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
                kept_span = get_span(kept)
                
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
                    # A longer matched span does not suppress a shorter candidate
                    # if the shorter candidate has stronger matching evidence (higher confidence)
                    if candidate.confidence > kept.confidence:
                        continue
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

    @staticmethod
    def _find_match_span_indices(q_words: list[str], val_normalized: str) -> list[int]:
        val_tokens = [t for t in val_normalized.split() if t]
        if not val_tokens:
            return []
        from semantic.matching.singular_plural_matcher import SingularPluralMatcher
        val_sings = [SingularPluralMatcher._to_singular(t) for t in val_tokens]
        q_sings = [SingularPluralMatcher._to_singular(t) for t in q_words]
        
        n_q = len(q_sings)
        n_v = len(val_sings)
        for i in range(n_q - n_v + 1):
            if q_sings[i:i+n_v] == val_sings:
                return list(range(i, i + n_v))
                
        val_sing_set = set(val_sings)
        indices = [i for i, q_sing in enumerate(q_sings) if q_sing in val_sing_set]
        return indices

    @staticmethod
    def _find_matching_dimension(word: str, dimension_context: list) -> str | None:
        if not word or not dimension_context:
            return None
        w = word.lower()
        for dim in dimension_context:
            bname = dim.get("business_name")
            if bname and bname.lower() == w:
                return bname
            dname = dim.get("dimension_name")
            if dname and dname.lower() == w:
                return bname or dname
            cname = dim.get("column_name")
            if cname and cname.lower() == w:
                return bname or cname
        if w in ["brand", "city", "state"]:
            return w.capitalize()
        return None