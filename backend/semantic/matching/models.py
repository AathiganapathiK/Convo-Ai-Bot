from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class MatchType(Enum):
    EXACT = "EXACT"
    NORMALIZED = "NORMALIZED"
    SINGULAR_PLURAL = "SINGULAR_PLURAL"
    FUZZY = "FUZZY"


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    value: str
    normalized_value: str
    confidence: float
    match_type: MatchType
    matched_question_tokens: List[str]
    matched_value_tokens: List[str]
    reason: str

    # Database mapping attributes
    dimension_id: Optional[int] = None
    business_name: Optional[str] = None
    table_name: Optional[str] = None
    column_name: Optional[str] = None

    # Gate 3 Step 21f - precise fuzzy token evidence.
    #
    # matched_question_tokens above records the SPAN the matcher searched
    # with: FuzzyMatcher sets it to the whole n-gram phrase, so "COTTON PANT"
    # and "LINEN PANT" both report ["cotton", "pant"] for the question
    # "cotton pant" even though only one of them explains "cotton". That
    # field is therefore unsafe as query-coverage evidence.
    #
    # This field records only the question token(s) a match actually
    # justifies - for FuzzyMatcher, the token
    # _has_token_level_evidence approved against this specific stored value.
    # Optional and defaulted, so every existing construction site (and every
    # other matcher, which does not set it) is unaffected.
    matched_question_tokens_precise: Optional[List[str]] = None


@dataclass(frozen=True)
class QuestionContext:
    raw_question: str
    normalized_question: str
    q_tokens: List[str]
    q_singulars: List[str]


@dataclass(frozen=True)
class CachedDimensionValue:
    semantic_dimension_id: int
    business_name: str
    table_name: str
    column_name: str
    value: str
    normalized_value: str

    # Pre-computed runtime tokens and singulars
    runtime_stored_norm: str
    runtime_stored_tokens: List[str]
    runtime_stored_singulars: List[str]
    runtime_raw_norm: str
    runtime_raw_tokens: List[str]
    runtime_raw_singulars: List[str]


@dataclass(frozen=True)
class MatchingContext:
    question_context: QuestionContext
    connection_id: str
    indexed_values: List[CachedDimensionValue]
    settings: Optional[dict] = None


@dataclass(frozen=True)
class MatchStatistics:
    exact_attempted: bool
    normalized_attempted: bool
    plural_attempted: bool
    fuzzy_attempted: bool

    # Retained for backward compatibility.
    #
    # The MatchingPipeline no longer determines a winning matcher.
    # All matchers are executed and the downstream MatchRanker determines
    # the final candidate ordering.
    winning_match: Optional[str]

    execution_time_ms: float

    # Number of candidates returned by each matcher.
    exact_match_count: int = 0
    normalized_match_count: int = 0
    plural_match_count: int = 0
    fuzzy_match_count: int = 0

    # Total candidates returned by all matchers.
    total_match_count: int = 0


class BaseMatcher:
    def match(self, context: MatchingContext) -> List[MatchResult]:
        raise NotImplementedError


class ResolutionStatus(Enum):
    NO_MATCH = "NO_MATCH"
    SINGLE_MATCH = "SINGLE_MATCH"
    WEAK_AMBIGUITY = "WEAK_AMBIGUITY"
    STRONG_AMBIGUITY = "STRONG_AMBIGUITY"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    # Gate 3 - the ambiguity-status contract. Two or more DISTINCT requested
    # concepts (different (table, column) targets - Brand and Category, City
    # and Division) each independently resolved, with no candidate ever asked
    # to out-compete a candidate for a different concept. Never assigned
    # unless classify() found more than one such target; see the grouping
    # step there.
    MULTI_MATCH = "MULTI_MATCH"


# Gate 3 Step 21d - RC-02. Three concrete words verified, by tracing real
# benchmark failures, to be generic filler that explains nothing about which
# value or dimension was meant ("total sales", "now show", "city instead").
# Kept separate from the global STOPWORDS set - which candidate_phrase_extractor,
# fuzzy_matcher and the Step 21a NO_MATCH guard also read - rather than adding
# to it, so this narrow, investigation-backed exemption cannot silently change
# behavior in those other consumers. Add a word here only when a specific
# failing case demonstrates it is genuinely never disambiguating, the same way
# these three were found; this is not a general-purpose stopword list.
RC02_FILLER_WORDS = {"total", "now", "instead"}



@dataclass
class AmbiguityChoice:
    """
    Represents an ambiguity choice, wrapping a MatchResult to prevent field duplication.
    """
    result: MatchResult
    actual_query_coverage: int = 0
    matched_query_tokens: List[str] = field(default_factory=list)

    @property
    def value(self) -> str:
        return self.result.value

    @property
    def normalized_value(self) -> str:
        return self.result.normalized_value

    @property
    def confidence(self) -> float:
        return self.result.confidence

    @property
    def match_type(self) -> MatchType:
        return self.result.match_type

    @property
    def dimension_id(self) -> Optional[int]:
        return self.result.dimension_id

    @property
    def business_name(self) -> Optional[str]:
        return self.result.business_name

    @property
    def table_name(self) -> Optional[str]:
        return self.result.table_name

    @property
    def column_name(self) -> Optional[str]:
        return self.result.column_name

    @property
    def matched_question_tokens(self) -> List[str]:
        return self.result.matched_question_tokens

    @property
    def matched_value_tokens(self) -> List[str]:
        return self.result.matched_value_tokens

    @property
    def reason(self) -> str:
        return self.result.reason


@dataclass(frozen=True)
class SemanticResolutionResult:
    status: ResolutionStatus
    candidates: List[AmbiguityChoice]
    dominant_match: Optional[AmbiguityChoice] = None
    # Populated only for MULTI_MATCH: one dominant candidate per distinct
    # (table, column) target, in place of the single `dominant_match` a
    # one-concept result carries. Every other status leaves this empty -
    # existing readers of `dominant_match` are unaffected.
    dominant_matches: List[AmbiguityChoice] = field(default_factory=list)


class AmbiguityClassifier:
    """
    Pure classifier for resolving semantic matching ambiguity based on:
    - Match type priority (EXACT > NORMALIZED > SINGULAR_PLURAL > FUZZY)
    - Confidence gap
    - Matched question span (evidence) length
    """

    @staticmethod
    def _type_priority(mt: MatchType) -> int:
        if mt == MatchType.EXACT:
            return 4
        if mt == MatchType.NORMALIZED:
            return 3
        if mt == MatchType.SINGULAR_PLURAL:
            return 2
        if mt == MatchType.FUZZY:
            return 1
        return 0

    @classmethod
    def _compute_query_coverage(cls, choice: AmbiguityChoice, q_tokens: List[str]) -> List[str]:
        if not q_tokens:
            return []

        # Avoid circular import issues by importing dynamically
        from semantic.matching.singular_plural_matcher import SingularPluralMatcher
        from semantic.matching.stopwords import STOPWORDS

        # 1. Normalize and get singulars of query tokens, filtering out stopwords
        q_map = {}
        for token in q_tokens:
            norm_t = SingularPluralMatcher._normalize_text(token)
            if norm_t and norm_t not in STOPWORDS:
                q_sing = SingularPluralMatcher._to_singular(norm_t)
                # Map singular form to the original token
                q_map[q_sing] = token

        # 2. Normalize and get singulars of candidate value tokens
        val_raw_tokens = []
        if choice.value:
            val_raw_tokens.extend(choice.value.split())
        if choice.normalized_value:
            val_raw_tokens.extend(choice.normalized_value.split())
        if choice.matched_value_tokens:
            val_raw_tokens.extend(choice.matched_value_tokens)

        val_singulars = set()
        for token in val_raw_tokens:
            norm_t = SingularPluralMatcher._normalize_text(token)
            if norm_t and norm_t not in STOPWORDS:
                val_sing = SingularPluralMatcher._to_singular(norm_t)
                val_singulars.add(val_sing)

        # 3. Intersect query singulars with candidate singulars
        matched = []
        for q_sing, q_raw in q_map.items():
            if q_sing in val_singulars:
                matched.append(q_raw)

        # 4. Gate 3 Step 21e - a FUZZY match already passed
        # FuzzyMatcher._has_token_level_evidence's token-level similarity
        # check at match time, and recorded exactly which question token it
        # was approved against in choice.result.matched_question_tokens.
        # Steps 1-3 above only ever credit a token that is IDENTICAL (up to
        # singular/plural) to one of the candidate's own STORED-VALUE
        # tokens - which a fuzzy/misspelled match can never satisfy by
        # definition: "coimbator" is not "coimbatore" even after
        # singularizing, no matter how good the fuzzy similarity was. That
        # silently discarded evidence the matcher had already approved,
        # instead of ever reading it.
        #
        # Additive only: EXACT, NORMALIZED and SINGULAR_PLURAL candidates
        # never take this branch, so steps 1-3 remain their only source of
        # matched tokens, unchanged. A token can be added here only if BOTH
        # the fuzzy matcher itself recorded it AND it is a real, non-stopword
        # token of the actual question (present in q_map) - never a token
        # invented for this check, and never a token the fuzzy matcher did
        # not already approve.
        #
        # Gate 3 - reads matched_question_tokens_precise, not the raw
        # matched_question_tokens above. The raw field is the whole n-gram
        # SPAN the matcher searched with, not what it actually approved -
        # "chennai city ramraj" for a fuzzy hit that only really explains
        # "ramraj" ("Show sales for Chennai city and Ramraj brand" fuzzy-
        # matched RAMRAJ PANT against a 3-token window). Crediting the whole
        # span here let that candidate's computed matched_query_tokens share
        # a token with an unrelated concept's candidates (CHENNAI,
        # ELECTRONIC CITY), which _competes() reads to decide what competes -
        # bridging two independently-qualified concepts (City, Brand) into
        # one false STRONG_AMBIGUITY tie instead of two MULTI_MATCH
        # resolutions. matched_question_tokens_precise is FuzzyMatcher's own
        # per-candidate answer to "which token did I actually approve this
        # against" (see fuzzy_matcher.py) and is always populated whenever a
        # FUZZY MatchResult is constructed at all - the one production
        # call site guarantees it, so this substitution never loses
        # evidence, only the accidental over-wide kind.
        if choice.result and choice.result.match_type == MatchType.FUZZY:
            for raw_tok in (choice.result.matched_question_tokens_precise or []):
                norm_t = SingularPluralMatcher._normalize_text(raw_tok)
                if not norm_t or norm_t in STOPWORDS:
                    continue
                sing_t = SingularPluralMatcher._to_singular(norm_t)
                q_raw = q_map.get(sing_t)
                if q_raw is not None and q_raw not in matched:
                    matched.append(q_raw)

        return matched

    @staticmethod
    def _competes(a, b) -> bool:
        """
        Do candidates `a` and `b` compete for the same requested concept?

        Gate 3 - ambiguity-status contract. Two things make a pair of
        candidates alternatives for what the user meant, rather than two
        different things the user asked for in the same breath:

          * they sit on the SAME physical column, so at most one of them can
            be true for a given row - VIVEAGHAM WHITE SHIRT and VIVEAGHAM
            COLOUR SHIRT both sit on Brand and cannot both be "the" brand
            meant; or
          * they were matched through the SAME question token(s) - Division
            replicated on three tables is matched via "vt" on all three, so
            even though the columns differ physically, all three are candidate
            answers to the identical word the user typed, and the existing
            table-affinity/specificity evidence is what should pick among
            them, unchanged.

        Two candidates that share neither - different columns AND disjoint
        question tokens, like Brand=RAMRAJ (from "ramraj") and
        Category=FRANCHISE (from "franchise category") - are never asked to
        out-compete each other; see the grouping step in classify().
        """
        res_a = getattr(a, "result", a)
        res_b = getattr(b, "result", b)
        same_column = (
            (getattr(res_a, "table_name", None) or "").lower()
            == (getattr(res_b, "table_name", None) or "").lower()
            and (getattr(res_a, "column_name", None) or "").lower()
            == (getattr(res_b, "column_name", None) or "").lower()
        )
        if same_column:
            return True
        tokens_a = set(getattr(a, "matched_query_tokens", None) or [])
        tokens_b = set(getattr(b, "matched_query_tokens", None) or [])
        return bool(tokens_a & tokens_b)

    @classmethod
    def _group_by_concept(cls, choices) -> List[List]:
        """
        Partition choices into groups that genuinely compete with each other
        (see _competes()), using connected components so competition is
        transitive: if A competes with B and B competes with C, all three
        stay one group even where A and C alone would not have merged.
        """
        n = len(choices)
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i, j):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

        for i in range(n):
            for j in range(i + 1, n):
                if cls._competes(choices[i], choices[j]):
                    union(i, j)

        groups: Dict[int, List] = {}
        for i, choice in enumerate(choices):
            groups.setdefault(find(i), []).append(choice)
        return list(groups.values())

    @classmethod
    def _resolve_group(cls, choices, q_tokens, dimension_meta, metric_tables):
        """
        Gate 3 Step 21b - evidence-based dominance, decided within ONE target
        (one physical column). Unchanged from the pre-Gate-3-ambiguity-status
        logic; classify() now calls this once per group instead of once over
        every match regardless of what each one was a candidate FOR.

        Returns (ResolutionStatus, dominant_choice_or_None). Only ever
        SINGLE_MATCH, WEAK_AMBIGUITY or STRONG_AMBIGUITY - PARTIAL_MATCH and
        MULTI_MATCH are decided by the caller, once, over the group results.
        """
        if len(choices) == 1:
            return ResolutionStatus.SINGLE_MATCH, choices[0]

        # This used to be four rules over eight hand-tuned thresholds, all
        # comparing MatchConfidence, which was a constant per matcher. Two
        # exact matches therefore had a confidence gap of exactly 0.00 and
        # no rule could ever fire, so the classifier returned
        # STRONG_AMBIGUITY whenever two candidates matched the same way -
        # regardless of how much of the question or of the stored value
        # each one actually explained.
        #
        # Now every candidate carries an evidence vector (see
        # matching/confidence.py) and the question asked first is
        # parameter-free: does one candidate beat another on EVERY signal?
        # Only when candidates genuinely trade off does a single margin
        # arbitrate. Eight tunable numbers become one.
        from semantic.matching.confidence import (
            DOMINANCE_MARGIN,
            score_candidates,
        )

        entity_tokens = q_tokens or []

        evidence = score_candidates(
            choices,
            entity_tokens=entity_tokens,
            dimension_meta=dimension_meta,
            metric_tables=metric_tables,
        )

        for choice, score in zip(choices, evidence):
            # Attached so a decision can be explained rather than asserted.
            try:
                object.__setattr__(choice, "evidence", score)
            except Exception:
                pass

        ranked = sorted(
            zip(choices, evidence), key=lambda pair: -pair[1].scalar
        )
        (c1, e1), (c2, e2) = ranked[0], ranked[1]

        if e1.dominates(e2):
            dominant = True
        else:
            dominant = (e1.scalar - e2.scalar) >= DOMINANCE_MARGIN

        if dominant:
            return ResolutionStatus.WEAK_AMBIGUITY, c1
        return ResolutionStatus.STRONG_AMBIGUITY, None

    @classmethod
    def classify(
        cls,
        matches: List[MatchResult],
        q_tokens: Optional[List[str]] = None,
        connection_id: Optional[str] = None,
        indexed_values: Optional[List[CachedDimensionValue]] = None,
        dimension_context: Optional[List[dict]] = None,
        current_metrics: Optional[List[dict]] = None,
        all_metrics: Optional[List[tuple]] = None,
        all_dimensions: Optional[List[tuple]] = None
    ) -> SemanticResolutionResult:
        if not matches:
            return SemanticResolutionResult(
                status=ResolutionStatus.NO_MATCH,
                candidates=[]
            )

        if q_tokens is None:
            # Fallback to extract from matches
            for m in matches:
                if m.matched_question_tokens:
                    q_tokens = m.matched_question_tokens
                    break
            if q_tokens is None:
                q_tokens = []

        # Convert matches and populate coverage
        choices = []
        for m in matches:
            choice = AmbiguityChoice(m)
            matched_toks = cls._compute_query_coverage(choice, q_tokens)
            choice.actual_query_coverage = len(matched_toks)
            choice.matched_query_tokens = matched_toks
            choices.append(choice)

        # What the administrator has said about each dimension. Absent on a
        # connection that has not been configured, in which case the signal
        # falls back to neutral rather than penalising anything. Computed
        # once, ahead of grouping, because every group's dominance decision
        # reads it.
        dimension_meta = {}
        for row in (all_dimensions or []):
            try:
                dimension_meta[row[0]] = {
                    "is_confirmed": bool(row[7]) if len(row) > 7 else False,
                    "dimension_role": row[6] if len(row) > 6 else None,
                }
            except (IndexError, TypeError):
                continue

        metric_tables = [
            m.get("table_name")
            for m in (current_metrics or [])
            if isinstance(m, dict)
        ]

        # Gate 3 - ambiguity-status contract. See _competes() for what makes
        # two candidates alternatives for one requested concept rather than
        # two different concepts requested together.
        groups = cls._group_by_concept(choices)

        # Left empty for the single-group path: dominant_match alone already
        # carries that result, exactly as before this change, and the
        # "dangerous unmatched tokens" check below falls back to it whenever
        # dominant_matches is empty. Only ever populated by the multi-group
        # branch, so a status of MULTI_MATCH is the only case a caller need
        # check to know this list matters (see resolve_matches()).
        dominant_matches: List[AmbiguityChoice] = []

        if len(groups) <= 1:
            result_status, dominant_match = cls._resolve_group(
                choices, q_tokens, dimension_meta, metric_tables
            )
        else:
            group_results = [
                cls._resolve_group(g, q_tokens, dimension_meta, metric_tables)
                for g in groups
            ]

            if any(
                status == ResolutionStatus.STRONG_AMBIGUITY
                for status, _ in group_results
            ):
                # One of the requested concepts itself has no dominant
                # candidate. The whole request cannot be answered
                # confidently, so this is not "some concepts resolved,
                # others not" (PARTIAL_MATCH) - it is a live competing
                # interpretation, same as the single-concept case.
                result_status = ResolutionStatus.STRONG_AMBIGUITY
                dominant_match = None
            else:
                # Every distinct requested concept resolved on its own -
                # this is the case the CRITICAL DISTINCTION guards: multiple
                # dimensions requested together is not ambiguity between
                # alternatives.
                result_status = ResolutionStatus.MULTI_MATCH
                dominant_match = None
                dominant_matches = [d for _, d in group_results if d is not None]

        # Check if the dominant match(es) have dangerous unmatched tokens.
        # Generalized from the single-dominant check: MULTI_MATCH carries
        # several dominants (one per concept), and a token none of them
        # explains is exactly as dangerous as one a lone dominant leaves
        # unexplained.
        dominants_to_check = (
            [dominant_match] if dominant_match is not None else dominant_matches
        )
        if result_status in (
            ResolutionStatus.SINGLE_MATCH,
            ResolutionStatus.WEAK_AMBIGUITY,
            ResolutionStatus.MULTI_MATCH,
        ) and dominants_to_check:
            explained_tokens = set()
            for d in dominants_to_check:
                explained_tokens.update(d.matched_query_tokens or [])
            unmatched_tokens = [t for t in q_tokens if t not in explained_tokens]
            if unmatched_tokens:
                from semantic.matching.singular_plural_matcher import SingularPluralMatcher

                # Every dominant's own dimension name, business name, column
                # name and synonyms are harmless - collected across all of
                # them so a MULTI_MATCH's second concept is exempted exactly
                # as its first one is.
                cand_dim_names = set()
                for dominant in dominants_to_check:
                    if not dominant.result:
                        continue
                    res = dominant.result
                    if res.business_name:
                        cand_dim_names.add(SingularPluralMatcher._to_singular(SingularPluralMatcher._normalize_text(res.business_name)))
                        norm = SingularPluralMatcher._normalize_text(res.business_name)
                        if norm:
                            for word in norm.replace(",", " ").split():
                                cand_dim_names.add(SingularPluralMatcher._to_singular(word))
                    if res.column_name:
                        cand_dim_names.add(SingularPluralMatcher._to_singular(SingularPluralMatcher._normalize_text(res.column_name)))
                        norm = SingularPluralMatcher._normalize_text(res.column_name)
                        if norm:
                            for word in norm.replace(",", " ").split():
                                cand_dim_names.add(SingularPluralMatcher._to_singular(word))
                    if all_dimensions and res.business_name:
                        for row in all_dimensions:
                            if isinstance(row, dict):
                                row_bus = row.get("business_name")
                                row_dim = row.get("dimension_name")
                                row_syns = row.get("synonyms")
                            else:
                                row_bus = row[1]
                                row_dim = row[0]
                                row_syns = row[4] if len(row) > 4 else None

                            if (row_bus and row_bus.lower() == res.business_name.lower()) or (row_dim and row_dim.lower() == res.business_name.lower()):
                                for f in [row_dim, row_bus, row_syns]:
                                    if f:
                                        norm = SingularPluralMatcher._normalize_text(str(f))
                                        if norm:
                                            for word in norm.replace(",", " ").split():
                                                cand_dim_names.add(SingularPluralMatcher._to_singular(word))

                # Gate 3 Step 21d - RC-02. A token the question already spent
                # on the METRIC ("pending" in "pending amount") was never
                # exempted here, only tokens belonging to the dimension the
                # value matched on. That is an arbitrary asymmetry: the
                # metric was resolved with exactly as much confidence as the
                # dimension, by the same pipeline, and a word it already
                # explains is no more dangerous than a word the dimension
                # explains. Reuses current_metrics (the metrics this request
                # already resolved) and all_metrics (already-loaded metadata,
                # the same list classify() already reads for all_dimensions)
                # to add synonyms - no new query, no new business vocabulary.
                if current_metrics and all_metrics:
                    resolved_metric_names = set()
                    for cm in current_metrics:
                        if isinstance(cm, dict) and cm.get("business_name"):
                            resolved_metric_names.add(cm["business_name"].lower())

                    for row in all_metrics:
                        if isinstance(row, dict):
                            row_bus = row.get("business_name")
                            row_metric = row.get("metric_name")
                            row_syns = row.get("synonyms")
                        else:
                            row_bus = row[1]
                            row_metric = row[0]
                            row_syns = row[5] if len(row) > 5 else None

                        if not row_bus or row_bus.lower() not in resolved_metric_names:
                            continue

                        for f in [row_metric, row_bus, row_syns]:
                            if f:
                                norm = SingularPluralMatcher._normalize_text(str(f))
                                if norm:
                                    for word in norm.replace(",", " ").split():
                                        cand_dim_names.add(SingularPluralMatcher._to_singular(word))

                has_dangerous_unmatched = False
                for t in unmatched_tokens:
                    norm_t = SingularPluralMatcher._normalize_text(t)
                    if not norm_t:
                        continue

                    # In simplified contract, any unmatched query token is dangerous unless
                    # it is a stopword, a verified-harmless filler word, or matches the
                    # candidate's own dimension/metric metadata.
                    from semantic.matching.stopwords import STOPWORDS
                    if norm_t in STOPWORDS or norm_t in RC02_FILLER_WORDS:
                        continue

                    sing_t = SingularPluralMatcher._to_singular(norm_t)
                    if sing_t not in cand_dim_names:
                        has_dangerous_unmatched = True
                        break

                if has_dangerous_unmatched:
                    result_status = ResolutionStatus.PARTIAL_MATCH



        return SemanticResolutionResult(
            status=result_status,
            candidates=choices,
            dominant_match=dominant_match,
            dominant_matches=dominant_matches
        )

