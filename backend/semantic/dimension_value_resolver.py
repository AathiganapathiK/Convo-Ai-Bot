from dataclasses import dataclass, replace as _dc_replace
from sqlalchemy import text
import os
import re
from database import engine

from semantic import runtime_config_filter

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

    # Step 4 - full scorer output, kept beside the converted MatchResults so
    # score/signals/provenance are not lost to a frozen dataclass.
    last_phrase_resolutions = []

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

    # ------------------------------------------------------------------
    # Step 3 - phrase-scoped matching
    # ------------------------------------------------------------------
    # Off unless SEMANTIC_VALUE_MODE=enforce. The path is complete and
    # tested either way; the flag decides whether production traffic uses
    # it, on the same shadow-then-enforce pattern SQL_GUARD_MODE uses.

    @staticmethod
    def _value_mode() -> str:
        return (os.getenv("SEMANTIC_VALUE_MODE", "legacy") or "").strip().lower()

    @classmethod
    def phrase_scoped_enabled(cls) -> bool:
        return cls._value_mode() in ("enforce", "candidate_scoped")

    @classmethod
    def candidate_scoped_enabled(cls) -> bool:
        """
        Step 4 - provider-backed candidates with deterministic scoring.

        A separate mode from `enforce` on purpose: `enforce` is bare
        phrase-scoping, which is what produced the Ramraj widening. Anything
        that opts into the new behaviour should opt into the scoring that
        makes it safe, so the two are not independently selectable.
        """
        return cls._value_mode() == "candidate_scoped"

    @classmethod
    def resolve_value_phrases(
        cls,
        connection_id: str,
        question: str,
        value_phrases: list,
        provider=None,
        judge=None,
    ):
        """
        Resolve each value phrase to real candidates, scored deterministically.

        Returns one PhraseResolution per usable phrase, in order. Phrases are
        resolved INDEPENDENTLY: each gets its own provider lookup and its own
        decision, so one phrase's candidates can never enter another's
        competitive set. Nothing here concatenates phrases.

        `provider` is injectable so this is testable with no database. It
        defaults to the real value index; whatever it is, candidates come from
        it and never from the extractor - the phrase only says what to look up.
        """
        from semantic.candidate_judge import apply_judge
        from semantic.candidate_scoring import resolve_phrase
        from semantic.value_provider import DbDimensionValueProvider

        if provider is None:
            provider = DbDimensionValueProvider(connection_id=connection_id)

        resolutions = []
        for phrase in value_phrases or []:
            text_value, dimension, qualifier_explicit = cls._phrase_fields(phrase)
            if not isinstance(text_value, str) or not text_value.strip():
                continue

            # The model's dimension is only honoured when the deterministic
            # qualifier check in Step 2 confirmed the user named it, AND the
            # name is one this provider actually serves. An unconfigured
            # dimension narrows nothing rather than narrowing to nothing.
            search_dimension = None
            if qualifier_explicit and isinstance(dimension, str) and dimension.strip():
                configured = {d.strip().lower() for d in (provider.dimensions() or [])}
                if dimension.strip().lower() in configured:
                    search_dimension = dimension

            candidates = provider.get_candidates(
                search_dimension, text_value, {"question": question}
            )
            resolution = resolve_phrase(
                candidates,
                text_value,
                question,
                qualifier_explicit=bool(search_dimension),
                phrase_dimension=search_dimension,
            )

            # The judge is consulted ONLY where deterministic ranking already
            # said the choice is genuinely ambiguous. apply_judge enforces
            # that, and enforces that the answer is one of these candidates,
            # so a clear winner is never second-guessed and an invented value
            # can never enter the plan.
            resolution = apply_judge(resolution, question, judge)

            resolutions.append(resolution)

        return resolutions

    @staticmethod
    def _phrase_fields(phrase):
        """
        (text, dimension, qualifier_explicit) from a ValuePhrase or its dict.

        Read structurally rather than by importing ai.extraction, so the
        semantic layer keeps no dependency on the extraction layer above it.
        """
        if isinstance(phrase, dict):
            return (
                phrase.get("phrase"),
                phrase.get("dimension"),
                bool(phrase.get("qualifier_explicit")),
            )
        return (
            getattr(phrase, "phrase", None),
            getattr(phrase, "dimension", None),
            bool(getattr(phrase, "qualifier_explicit", False)),
        )

    def _candidate_scoped_matches(self, value_phrases, connection_id, question, provider=None, judge=None):
        """
        Step 4 integration: provider -> scorer -> MatchResult.

        Each phrase is resolved independently and converted separately, so a
        phrase's candidates only ever carry that phrase's tokens and can never
        compete with another phrase's downstream. The full PhraseResolution
        objects are kept on the resolver as `last_phrase_resolutions` so the
        score, the signals and the provenance survive a conversion that
        MatchResult has no fields for.
        """
        from semantic.candidate_scoring import to_match_results
        from semantic.matching import MatchStatistics

        resolutions = self.resolve_value_phrases(
            connection_id, question, value_phrases, provider=provider, judge=judge
        )
        self.last_phrase_resolutions = resolutions
        type(self).last_phrase_resolutions = resolutions

        if not resolutions:
            return None, None

        matches = []
        for resolution in resolutions:
            matches.extend(to_match_results(resolution))

        exact = sum(1 for m in matches if m.match_type == MatchType.EXACT)
        normalized = sum(1 for m in matches if m.match_type == MatchType.NORMALIZED)
        fuzzy = sum(1 for m in matches if m.match_type == MatchType.FUZZY)

        stats = MatchStatistics(
            exact_attempted=True,
            normalized_attempted=True,
            plural_attempted=False,
            fuzzy_attempted=True,
            winning_match=None,
            execution_time_ms=0.0,
            exact_match_count=exact,
            normalized_match_count=normalized,
            plural_match_count=0,
            fuzzy_match_count=fuzzy,
            total_match_count=len(matches),
        )
        return matches, stats

    def _phrase_scoped_matches(self, value_phrases, connection_id, indexed_values):
        """
        Run the existing matcher pipeline once per value phrase.

        This is the whole of Step 3's behavioural change. Every matcher, the
        cached value index, and all downstream ranking/ambiguity logic are
        untouched - the only difference is WHAT the matchers are asked to
        explain. Previously they were handed the entire question and generated
        every 1-3 word n-gram of it; now they are handed one phrase the
        extractor identified, so a verb or a metric word in some other part of
        the sentence can no longer become a candidate database value.

        Candidate values still come only from `indexed_values`, which is the
        real configured value index. Nothing here can produce a value the
        database does not contain.

        Each phrase is matched against its own context, so one phrase's
        candidates cannot contaminate another's: "Chennai city and Ramraj
        brand" produces two independent candidate sets rather than one shared
        pool that the downstream competition logic could bridge.
        """
        all_matches = []
        merged = None

        for phrase in value_phrases or []:
            text_value, dimension, qualifier_explicit = self._phrase_fields(phrase)

            if not isinstance(text_value, str) or not text_value.strip():
                continue

            sanitized = QuestionSanitizer.sanitize(text_value)
            normalized = self._normalize_text(sanitized)
            tokens = [t for t in normalized.split() if t not in STOPWORDS]
            if not tokens:
                continue

            scoped_values = indexed_values

            # An explicit qualifier the USER wrote ("Chennai city") narrows the
            # search to that dimension. qualifier_explicit was computed
            # deterministically from the question in Step 2, never taken from
            # the model, so this is the user's own restriction being honoured.
            # A bare value is deliberately left unrestricted, because its
            # ambiguity across dimensions is real and belongs downstream.
            if qualifier_explicit and isinstance(dimension, str) and dimension.strip():
                wanted = dimension.strip().lower()
                narrowed = [
                    v for v in indexed_values
                    if (v.business_name or "").strip().lower() == wanted
                ]
                # If the configured dimension indexes no values, fall back to
                # the full set rather than manufacturing an unresolved phrase.
                if narrowed:
                    scoped_values = narrowed

            context = MatchingContext(
                question_context=QuestionContext(
                    raw_question=sanitized,
                    normalized_question=normalized,
                    q_tokens=tokens,
                    q_singulars=[SingularPluralMatcher._to_singular(t) for t in tokens],
                ),
                connection_id=connection_id,
                indexed_values=scoped_values,
                settings=self.settings,
            )

            matches, stats = self.pipeline.execute(context)
            all_matches.extend(matches or [])

            if merged is None:
                merged = stats
            else:
                merged = _dc_replace(
                    merged,
                    exact_attempted=merged.exact_attempted or stats.exact_attempted,
                    normalized_attempted=merged.normalized_attempted or stats.normalized_attempted,
                    plural_attempted=merged.plural_attempted or stats.plural_attempted,
                    fuzzy_attempted=merged.fuzzy_attempted or stats.fuzzy_attempted,
                    execution_time_ms=merged.execution_time_ms + stats.execution_time_ms,
                    exact_match_count=merged.exact_match_count + stats.exact_match_count,
                    normalized_match_count=merged.normalized_match_count + stats.normalized_match_count,
                    plural_match_count=merged.plural_match_count + stats.plural_match_count,
                    fuzzy_match_count=merged.fuzzy_match_count + stats.fuzzy_match_count,
                    total_match_count=merged.total_match_count + stats.total_match_count,
                )

        return all_matches, merged

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
        all_dimensions: list = None,
        metric_claimed_tokens: set = None,
        value_phrases: list = None,
        value_provider=None,
        value_judge=None
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
            all_dimensions,
            metric_claimed_tokens,
            value_phrases,
            value_provider,
            value_judge
        )
        cls.last_match_stats = resolver.last_match_stats
        cls.last_resolution_result = resolver.last_resolution_result
        cls.last_followup_context = getattr(resolver, "followup_context", None)
        return results

    @classmethod
    def resolve_phrases(cls, connection_id: str, question: str, value_phrases: list, **kwargs):
        """
        Step 3's dedicated phrase-scoped entry point.

        Identical to resolve() with value_phrases supplied; named separately so
        a caller can state the intent explicitly and so the phrase path is
        testable without going through the whole-question signature. Still
        honours phrase_scoped_enabled(): with the flag off this behaves exactly
        like resolve(), which is what keeps the rollout controlled.
        """
        return cls.resolve(connection_id, question, value_phrases=value_phrases, **kwargs)

    def resolve_matches(
        self,
        connection_id: str,
        question: str,
        clarified_candidate: dict = None,
        dimension_context: list = None,
        previous_semantic_context: dict = None,
        current_metrics: list = None,
        all_metrics: list = None,
        all_dimensions: list = None,
        metric_claimed_tokens: set = None,
        value_phrases: list = None,
        value_provider=None,
        value_judge=None
    ):

        """
        Resolve matches using the injected matching pipeline.

        `value_phrases` (Step 3, optional) are the spans the extractor
        identified as values. When supplied and the phrase-scoped path is
        enabled, the matchers are asked to explain those phrases instead of
        the whole question. Everything else is unchanged.
        """
        if clarified_candidate:
            candidates_list = clarified_candidate if isinstance(clarified_candidate, list) else [clarified_candidate]
            non_temp_candidates = []
            for cand in candidates_list:
                if isinstance(cand, dict):
                    val = cand.get("value")
                    val_lower = val.lower() if val else ""
                    if val_lower not in ("this year", "last year", "2 years ago", "3 years ago", "4 years ago"):
                        non_temp_candidates.append(cand)

            if non_temp_candidates:
                clarified = non_temp_candidates[0]
                # MatchResult, MatchType, AmbiguityChoice, ResolutionStatus and
                # SemanticResolutionResult are already imported at module scope
                # (see the semantic.matching import block above). A local
                # import of the same names here made every one of them a local
                # variable for the whole resolve() method under Python's
                # function-scoping rules - any reference to e.g.
                # ResolutionStatus reached before this branch executed UnboundLocalError'd,
                # which is exactly what surfaced when the WEAK_AMBIGUITY fix
                # below added the first such reference outside this branch.
                m = MatchResult(
                    matched=True,
                    value=clarified["value"],
                    normalized_value=clarified.get("normalized_value", clarified["value"].lower()),
                    confidence=clarified.get("confidence", 1.0),
                    match_type=MatchType(clarified.get("match_type", "EXACT")),
                    matched_question_tokens=clarified.get("matched_question_tokens", []),
                    matched_value_tokens=clarified.get("matched_value_tokens", []),
                    reason="Clarified by user",
                    dimension_id=clarified.get("dimension_id"),
                    business_name=clarified.get("business_name") or clarified.get("dimension"),
                    table_name=clarified.get("table_name"),
                    column_name=clarified.get("column_name")
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
        
        # Step 3. Phrase-scoped production replaces whole-question n-gram
        # production when the extractor supplied phrases AND the path is
        # enabled. Everything after this point is unchanged and still reads
        # the whole question's tokens, so ranking, containment, competition
        # and ambiguity classification behave exactly as before.
        phrase_matches, phrase_stats = None, None
        candidate_scoped_matches = False
        if value_phrases and self.candidate_scoped_enabled():
            candidate_scoped_matches = True
            # Provider-backed candidates, deterministically scored, converted
            # into the ordinary MatchResult representation. Everything below
            # this line is the existing engine and does not know the difference.
            phrase_matches, phrase_stats = self._candidate_scoped_matches(
                value_phrases, connection_id, question, value_provider, value_judge
            )
        elif value_phrases and self.phrase_scoped_enabled():
            phrase_matches, phrase_stats = self._phrase_scoped_matches(
                value_phrases, connection_id, indexed_values
            )

        if phrase_stats is not None:
            # At least one usable phrase ran. An empty match list here is a
            # real answer - this question filters on something the database
            # does not contain - and must not fall back to the whole question.
            matches, stats = phrase_matches, phrase_stats
        else:
            # No phrases, or every phrase was malformed: legacy path, unchanged.
            matches, stats = self.pipeline.execute(matching_context)
        self.last_match_stats = stats

        if matches:
            # Step 1:
            # Different matchers may return the same indexed value.
            # Consolidate those duplicate pieces of evidence first.
            matches = self._consolidate_duplicate_matches(matches)

            # Step 2:
            # Remove genuinely contained candidate values.
            # Containment removal exists to undo whole-question n-gram
            # over-generation: a longer value that explains no additional
            # question token is noise the matchers produced, not a candidate a
            # user could have meant. The candidate-scoped path does not
            # over-generate - the scorer has already weighed each candidate
            # against the phrase AND the question and decided which ones
            # genuinely compete. Re-running this pass on its output silently
            # discards that decision: "Show sales for Ramraj" went from an
            # AMBIGUOUS four-way family to SINGLE_MATCH, losing the
            # clarification the user needed. Every other pass - consolidation,
            # metric subsumption, competition, the ambiguity classifier and
            # reachability - still runs on both paths.
            if not candidate_scoped_matches:
                matches = self._remove_contained_matches(matches, q_tokens)

            # Step 2b - Gate 3. A configured multi-word METRIC phrase already
            # explained some of the question's tokens; a value candidate that
            # explains nothing beyond those same tokens is not genuine
            # dimension/value evidence, it is the metric's own words being
            # re-matched against an unrelated column. "Show due amount for
            # Chennai city" configures "due amount" as a Pending Amount
            # synonym - once that synonym has claimed "due" and "amount",
            # every DueStatus label that only overlaps the question on "due"
            # (NO DUE, OVER DUE, Future Due, ...) is dropped. A candidate that
            # explains a token the metric did NOT claim survives untouched:
            # "due today" contributes "today", "delayed due" contributes
            # "delayed", so those stay live business qualifiers. Generic: no
            # word, table or column is named here - only whichever tokens the
            # metric phrase this connection's own configuration matched.
            if matches and metric_claimed_tokens:
                matches = self._drop_metric_subsumed_matches(
                    matches, q_tokens, metric_claimed_tokens
                )

            # A word the temporal layer already read as intent is not a value.
            #
            # Distinct from the metric filter above, which asks whether the
            # VALUE's own words are all metric words. This asks the other
            # question: which question token did this candidate actually get
            # approved against? "Show sales trend" was resolved as a
            # TrendIntent and then fuzzy-matched "trend" to the product value
            # "CCB TRENDY" - whose own words are not metric words, so the
            # filter above correctly let it through. The evidence that fails
            # is the question side: the only token it explains was already
            # spent on the intent.
            if matches:
                matches = self._drop_intent_claimed_matches(matches)

            # Apply explicit dimension context filtering if dimension_context or all_dimensions is provided
            if not dimension_context and all_dimensions:
                dimension_context = [
                    {
                        "dimension_name": row[0] if len(row) > 0 else None,
                        "business_name": row[1] if len(row) > 1 else None,
                        "table_name": row[2] if len(row) > 2 else None,
                        "column_name": row[3] if len(row) > 3 else None,
                        "synonyms": row[4] if len(row) > 4 else None,
                    }
                    for row in all_dimensions
                ]
            elif dimension_context and all_dimensions:
                syn_map = {}
                for row in all_dimensions:
                    bname = (row[1] or row[0] or "").lower()
                    if bname and len(row) > 4:
                        syn_map[bname] = row[4]
                for d in dimension_context:
                    if not d.get("synonyms"):
                        bname = (d.get("business_name") or d.get("dimension_name") or "").lower()
                        if bname in syn_map:
                            d["synonyms"] = syn_map[bname]

            has_explicit_label = False
            if dimension_context:
                q_words = normalized_question.split()
                filtered_matches = []
                for m in matches:
                    val_norm = m.normalized_value or m.value.lower()
                    indices = self._find_match_span_indices(q_words, val_norm)

                    # Gate 3 Step 17a. The lookup above finds the value by its
                    # own spelling, so it can never locate a FUZZY match: the
                    # question said "coimbator" and the stored value is
                    # "COIMBATORE". With no span there are no adjacent words,
                    # so the qualifier below never fired and "coimbator city"
                    # kept District=COIMBATORE alongside City=COIMBATORE -
                    # while the exactly-spelled "Chennai city" correctly
                    # dropped District.
                    #
                    # matched_question_tokens_precise (added in 21f) holds the
                    # token the fuzzy matcher actually approved for THIS
                    # candidate, which does appear in the question and can
                    # therefore be located. matched_question_tokens is
                    # deliberately NOT used: it is the whole n-gram span the
                    # matcher searched with, which would point at the wrong
                    # words. The shared helper is reused unchanged, and this
                    # only runs when the existing lookup found nothing, so
                    # exact/normalized/singular-plural behaviour is untouched.
                    if not indices and m.match_type == MatchType.FUZZY:
                        precise_tokens = m.matched_question_tokens_precise or []
                        if precise_tokens:
                            indices = self._find_match_span_indices(
                                q_words, " ".join(precise_tokens)
                            )

                    explicit_dim = None
                    if indices:
                        min_idx = min(indices)
                        max_idx = max(indices)
                        adjacent_phrases = []
                        # Check n-gram phrases (3-gram, 2-gram, 1-gram) after max_idx
                        for n in (3, 2, 1):
                            if max_idx + n < len(q_words):
                                phrase = " ".join(q_words[max_idx + 1 : max_idx + 1 + n])
                                adjacent_phrases.append(phrase)
                        # Check n-gram phrases (3-gram, 2-gram, 1-gram) before min_idx
                        for n in (3, 2, 1):
                            if min_idx - n >= 0:
                                phrase = " ".join(q_words[min_idx - n : min_idx])
                                adjacent_phrases.append(phrase)

                        for phrase in adjacent_phrases:
                            matched_dim_name = self._find_matching_dimension(phrase, dimension_context)
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


            # Map back to dicts for backward compatibility across downstream components (e.g. PromptBuilder).
            #
            # SINGLE_MATCH only: collapse to the one dominant match. There is
            # nothing else to preserve - the ranker already discarded every
            # other candidate before classification saw this question - and SQL
            # generation for a single-candidate result must not see cross-talk
            # from candidates that were never really in contention.
            def _choice_dict(choice):
                m = choice.result
                # A curated family stands for the rows it groups, so it carries
                # them here. Downstream builds one IN filter over the members
                # instead of an equality filter on a name that is not itself a
                # stored value. Empty for every ordinary value, which leaves
                # their handling untouched.
                members = self._members_of(
                    connection_id, m.table_name, m.column_name, m.value
                )
                return {
                    "dimension_id": m.dimension_id,
                    "business_name": m.business_name,
                    "table_name": m.table_name,
                    "column_name": m.column_name,
                    "value": m.value,
                    "normalized_value": m.normalized_value,
                    "confidence": m.confidence,
                    "match_type": m.match_type.value,
                    # Use clean matched_query_tokens from classifier to avoid pollution
                    "matched_question_tokens": choice.matched_query_tokens,
                    "matched_value_tokens": m.matched_value_tokens,
                    "reason": m.reason,
                    "family_members": list(members),
                }

            if (
                self.last_resolution_result.status == ResolutionStatus.SINGLE_MATCH
                and self.last_resolution_result.dominant_match
            ):
                dom_choice = self.last_resolution_result.dominant_match
                return ResolutionResultList(
                    [_choice_dict(dom_choice)],
                    resolution_result=self.last_resolution_result,
                    followup_context=getattr(self, "followup_context", None),
                    match_stats=self.last_match_stats
                )

            # MULTI_MATCH, and PARTIAL_MATCH reached by way of MULTI_MATCH (a
            # dangerous unmatched token downgraded it - see classify()): every
            # distinct requested concept already resolved to its own single
            # dominant candidate, so there is nothing to disambiguate between
            # them. One row per concept, same as SINGLE_MATCH's one row for
            # its one concept.
            #
            # dominant_matches is populated ONLY by classify()'s multi-group
            # path - a single-group SINGLE_MATCH/WEAK_AMBIGUITY leaves it
            # empty and is already handled above/below via dominant_match -
            # so this can never intercept those and skip the "genuine
            # alternative" expansion a WEAK_AMBIGUITY result depends on.
            if self.last_resolution_result.dominant_matches:
                return ResolutionResultList(
                    [_choice_dict(c) for c in self.last_resolution_result.dominant_matches],
                    resolution_result=self.last_resolution_result,
                    followup_context=getattr(self, "followup_context", None),
                    match_stats=self.last_match_stats
                )

            # WEAK_AMBIGUITY (the only other status carrying a dominant_match -
            # classify() leaves it None for STRONG_AMBIGUITY):
            #
            # 21b's confidence model picked a preferred candidate, but
            # WEAK_AMBIGUITY means alternatives remain live for clarification -
            # collapsing to one here made the level indistinguishable from
            # SINGLE_MATCH. Keeping every candidate unconditionally was tried
            # next and over-corrected: a question ending in "city" also fuzzy-
            # matches the stored value "ELECTRONIC CITY" on the same City
            # column, and "Banians" singular/plural-matches an unrelated
            # internal code "SECONDS_ RN BANIAN" on a different column. Neither
            # is a competing answer to the question; both are matches on a
            # token, or a substring, that isn't what the user was asking about.
            #
            # A candidate is a GENUINE alternative - one the user might really
            # have meant - only when it competes with the dominant candidate on
            # the same ground: the same physical column, matched through at
            # least one of the same question tokens the dominant candidate
            # itself was matched through. "Chennai city" and "ELECTRONIC CITY"
            # share the column but not a token (chennai vs city - disjoint).
            # "Banians" and "SECONDS_ RN BANIAN" share the token but not the
            # column (ProdGrp1 vs ProdGrp3). "children wear" against ETHNIC
            # WEAR and N--NIGHT WEARS share both - same ProdGrp2 column, both
            # matched via "wear" - so both stay, and the existing clarification
            # flow decides between them as it always has.
            if self.last_resolution_result.dominant_match:
                dom_choice = self.last_resolution_result.dominant_match
                dom_tokens = set(dom_choice.matched_query_tokens or [])

                def _is_genuine_alternative(choice):
                    same_column = (
                        choice.table_name == dom_choice.table_name
                        and choice.column_name == dom_choice.column_name
                    )
                    shares_matched_token = bool(
                        dom_tokens & set(choice.matched_query_tokens or [])
                    )
                    return same_column and shares_matched_token

                ordered = [dom_choice] + [
                    choice for choice in self.last_resolution_result.candidates
                    if choice is not dom_choice and _is_genuine_alternative(choice)
                ]
                return ResolutionResultList(
                    [_choice_dict(choice) for choice in ordered],
                    resolution_result=self.last_resolution_result,
                    followup_context=getattr(self, "followup_context", None),
                    match_stats=self.last_match_stats
                )

            # Otherwise (e.g. STRONG_AMBIGUITY), return all candidates with clean matched_question_tokens
            # so they are returned in semantic_result for the UI/clarification.
            #
            # Gate 3 - a genuine tie is not worth asking about when EVERY tied
            # candidate sits on a table unreachable from the resolved
            # metric's table. "Show sales for Chennai" ties City against
            # District (both on PBI_OUTSTANDING_ENES_SUMMARY, neither
            # reachable from Sales) - classify() correctly could not break
            # that tie on its own evidence (table_affinity is 0 for both, so
            # it cannot discriminate), but asking the user to pick between
            # two answers that are both dead ends is not a real
            # clarification. This runs strictly AFTER classify() has already
            # decided the tie exists - it never influences which candidates
            # competed or who would have won, so it cannot reproduce the
            # regressions candidate-level filtering caused (VT's Division
            # still wins over btype via table_affinity INSIDE classify(),
            # long before this code ever runs, because that tie is NOT
            # all-unreachable - Division is on the metric's own table). If
            # even one candidate is reachable, the full tied set is returned
            # exactly as before - only an all-unreachable tie collapses to
            # empty, falling through to the resolver's existing unresolved-
            # value handling (Step 21a) instead of a clarification prompt
            # that can never be satisfied either way it is answered.
            #
            # Reuses RelationshipExpander.build_graph() - the exact graph
            # SemanticGate itself checks - so nothing is judged reachable or
            # unreachable here that SemanticGate would not also decide.
            # Fails open (keeps the full tied set) on any lookup error.
            #
            # Gated on `not has_explicit_label`: "coimbator city" ties
            # COIMBATORE against a fuzzy false-positive, ELECTRONIC CITY -
            # both on the same unreachable table, but the user explicitly
            # named the dimension ("city"), so this is a which-VALUE tie
            # within a deliberately chosen business concept, not a
            # which-DIMENSION-and-is-any-of-them-even-real tie like bare
            # "Chennai". An explicitly qualified tie is left exactly as
            # before regardless of table reachability - only a tie with no
            # qualifier at all is eligible to collapse.
            candidates = self.last_resolution_result.candidates
            if candidates and current_metrics and not has_explicit_label:
                metric_tables = {
                    (m.get("table_name") or "").strip().upper()
                    for m in current_metrics
                    if isinstance(m, dict) and m.get("table_name")
                }
                metric_tables.discard("")

                if metric_tables:
                    try:
                        from collections import deque
                        from semantic.relationship_expander import RelationshipExpander

                        raw_graph = RelationshipExpander.build_graph(connection_id)
                        graph = {}
                        for src, targets in raw_graph.items():
                            key = src.strip().upper()
                            graph.setdefault(key, set()).update(
                                t.strip().upper() for t in targets
                            )

                        reachable_cache = {}

                        def _is_reachable(table_name_raw):
                            table = (table_name_raw or "").strip().upper()
                            if not table or table in metric_tables:
                                return True
                            if table in reachable_cache:
                                return reachable_cache[table]
                            found = False
                            for start in metric_tables:
                                queue = deque([start])
                                visited = {start}
                                while queue:
                                    curr = queue.popleft()
                                    if curr == table:
                                        found = True
                                        break
                                    for nxt in graph.get(curr, set()):
                                        if nxt not in visited:
                                            visited.add(nxt)
                                            queue.append(nxt)
                                if found:
                                    break
                            reachable_cache[table] = found
                            return found

                        if not any(_is_reachable(c.table_name) for c in candidates):
                            candidates = []
                    except Exception:
                        pass  # fail open - keep the full tied set

            return ResolutionResultList(
                [_choice_dict(choice) for choice in candidates],
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

        # Gate 3 P0 - an excluded dimension must not supply candidate values.
        #
        # Without this an excluded column still fed the matcher, so excluding a
        # duplicate State column removed nothing: its values kept producing the
        # cross-dimension ambiguity the exclusion was meant to settle.
        query = text(f"""
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
                {runtime_config_filter.dimension_filter("sd")}
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

        cached_values.extend(self._family_candidates(connection_id))

        self.cache.put(connection_id, cached_values)
        return cached_values

    def _family_candidates(self, connection_id: str) -> list[CachedDimensionValue]:
        """
        Curated value families, offered to the matchers as if they were stored
        values.

        WHY THE FAMILY IS A CANDIDATE RATHER THAN A POST-MATCH RULE

        Some dimensions store a composite key instead of the entity a user
        names. Brand holds brand x product-line pairs, so "Ramraj" matches no
        stored value: every matcher fell through to fuzzy, and the 2-gram
        "ramraj brand" scored 0.85 against RAMRAJ LITTLESTARS - just over the
        cutoff. That longer span then suppressed the honest single-token
        matches through span containment, leaving one arbitrary product line
        standing alone as a confident SINGLE_MATCH.

        Making the family a first-class candidate fixes that at the root. The
        question token "ramraj" now matches the family value RAMRAJ EXACTLY, so
        it beats every fuzzy member on tier, on value coverage, and on the
        containment rule's own confidence guard - a shorter span survives a
        longer one when its evidence is stronger. The user's word matches a
        real configured thing instead of a near-miss on a narrower one.

        Membership is never inferred here; see semantic/value_family.py. A
        family the administrator has not confirmed, or one with fewer than two
        members, is not offered at all - the resolver then behaves exactly as
        it did before families existed, which surfaces the ambiguity rather
        than answering from configuration nobody approved.
        """
        from semantic.value_family import ValueFamilyLoader

        try:
            config = ValueFamilyLoader.for_connection(connection_id)
        except Exception:
            return []

        candidates = []
        for family in config.usable():
            norm_raw = self._normalize_text(family.family_name)
            tokens = [t for t in norm_raw.split() if t not in STOPWORDS]
            singulars = [SingularPluralMatcher._to_singular(t) for t in tokens]

            candidates.append(CachedDimensionValue(
                semantic_dimension_id=family.dimension_id,
                business_name=family.business_name,
                table_name=family.table_name,
                column_name=family.column_name,
                value=family.family_name,
                normalized_value=norm_raw,
                runtime_stored_norm=norm_raw,
                runtime_stored_tokens=tokens,
                runtime_stored_singulars=singulars,
                runtime_raw_norm=norm_raw,
                runtime_raw_tokens=tokens,
                runtime_raw_singulars=singulars,
            ))

        return candidates

    @staticmethod
    def _members_of(connection_id, table_name, column_name, value) -> tuple:
        """
        The configured members of a matched value, or () if it is not a family.

        Consulted where resolved values are handed downstream, so a family
        expands to the rows it stands for without any matcher needing to know
        families exist.

        Reads the loader rather than any state left behind by
        _family_candidates: that only runs when the value cache misses, so
        instance state would be empty on every cached request. ValueFamilyLoader
        keeps its own TTL cache, so this stays a dictionary lookup in the
        normal case.
        """
        if not value or not connection_id:
            return ()

        try:
            from semantic.value_family import ValueFamilyLoader
            config = ValueFamilyLoader.for_connection(connection_id)
        except Exception:
            return ()

        return config.members_for(table_name, column_name, value)

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
    @staticmethod
    def _drop_intent_claimed_matches(matches: list) -> list:
        """
        Drop value matches whose only question evidence was an intent word.

        Reads `matched_question_tokens_precise` - the token a matcher actually
        approved a candidate against, not the wider span it searched with -
        so a candidate that explains anything the time expression did not is
        untouched. With no temporal expression nothing is claimed and this is
        a no-op, which is why it can run unconditionally.
        """
        try:
            from semantic.temporal.detector import get_claimed_tokens
            claimed = {t.lower() for t in (get_claimed_tokens() or set())}
        except Exception:
            claimed = set()

        if not claimed:
            return matches

        survivors = []
        for m in matches:
            precise = {
                str(t).lower()
                for t in (getattr(m, "matched_question_tokens_precise", None) or [])
                if str(t).strip()
            }
            if precise and precise <= claimed:
                continue
            survivors.append(m)

        return survivors

    @staticmethod
    def _drop_metric_subsumed_matches(
        matches: list[MatchResult], q_tokens: list[str], metric_claimed_tokens: set
    ) -> list[MatchResult]:
        """
        Drop a value candidate whose entire question evidence was already
        spent on a configured metric phrase - see the call site in
        resolve_matches() for the "due amount" / DueStatus example this
        exists for.

        A candidate survives if it explains at least one question token
        `metric_claimed_tokens` does NOT cover - genuine additional evidence,
        singular/plural normalized so "days" vs "day" is not treated as new.
        A candidate that explains no question token at all (nothing to
        compare) is left untouched; this filter only ever removes a
        candidate whose explained tokens are a non-empty subset of the
        metric's own claimed tokens.
        """
        claimed = {SingularPluralMatcher._to_singular(t.lower()) for t in metric_claimed_tokens}
        if not claimed:
            return matches

        q_singulars = {SingularPluralMatcher._to_singular(t.lower()) for t in q_tokens}

        survivors = []
        for m in matches:
            value_singulars = {
                SingularPluralMatcher._to_singular(SingularPluralMatcher._normalize_text(t))
                for t in (m.matched_value_tokens or [])
                if t and SingularPluralMatcher._normalize_text(t) not in STOPWORDS
            }
            explained = value_singulars & q_singulars
            if explained and explained <= claimed:
                continue
            survivors.append(m)

        return survivors

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
        w = word.lower().strip()

        # Gate 3 Step 19b - recognise a plural qualifier.
        w_singular = SingularPluralMatcher._to_singular(w)

        def _same(candidate: str) -> bool:
            if not candidate:
                return False
            c = str(candidate).lower().strip()
            c_norm = c.replace("grp", "group").replace("prod", "product")
            w_norm = w.replace("grp", "group").replace("prod", "product")
            if c == w or c_norm == w_norm:
                return True
            return (
                SingularPluralMatcher._to_singular(c) == w_singular
                or SingularPluralMatcher._to_singular(c_norm) == SingularPluralMatcher._to_singular(w_norm)
            )

        def _get_val(dim_item, key):
            if hasattr(dim_item, "_mapping"):
                return dim_item._mapping.get(key)
            elif isinstance(dim_item, dict):
                return dim_item.get(key)
            return getattr(dim_item, key, None)

        for dim in dimension_context:
            bname = _get_val(dim, "business_name")
            if _same(bname):
                return bname
            dname = _get_val(dim, "dimension_name")
            if _same(dname):
                return bname or dname
            cname = _get_val(dim, "column_name")
            if _same(cname):
                return bname or cname

            syns = _get_val(dim, "synonyms")
            if syns:
                if isinstance(syns, str):
                    syn_list = [s.strip() for s in syns.replace(";", ",").split(",") if s.strip()]
                elif isinstance(syns, list):
                    syn_list = syns
                else:
                    syn_list = []
                for syn in syn_list:
                    if _same(syn):
                        return bname or dname or cname

        if w in ["brand", "city", "state"]:
            return w.capitalize()
        return None