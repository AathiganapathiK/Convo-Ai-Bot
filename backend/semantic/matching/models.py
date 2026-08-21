from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


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

        return matched

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

        if len(choices) == 1:
            result_status = ResolutionStatus.SINGLE_MATCH
            dominant_match = choices[0]
        else:
            # Multiple candidates. Compare Rank 1 (choices[0]) against Rank 2 (choices[1])
            c1 = choices[0]
            c2 = choices[1]

            p1 = cls._type_priority(c1.match_type)
            p2 = cls._type_priority(c2.match_type)
            priority_gap = p1 - p2

            len1 = c1.actual_query_coverage
            len2 = c2.actual_query_coverage

            conf_gap = c1.confidence - c2.confidence

            dominant = False

            # Rule 1: High priority gap (gap >= 2, e.g. EXACT vs FUZZY) is dominant
            # if the confidence of c1 is not significantly worse than c2
            # AND c1 covers at least as many query tokens as c2.
            # Without the coverage guard, a partial EXACT match (e.g. "Cotton"
            # covering 1/2 tokens) would incorrectly dominate a full-coverage
            # SINGULAR_PLURAL match (e.g. "Cotton Pants" covering 2/2 tokens).
            if priority_gap >= 2:
                if c1.confidence >= c2.confidence - 0.10 and len1 >= len2:
                    dominant = True

            # Rule 2: c1 has more matched question tokens (evidence span) than c2
            # and equal/better priority, and confidence is not significantly worse.
            # We allow up to an 8% confidence penalty for a better coverage match.
            elif len1 > len2 and p1 >= p2 and c1.confidence >= c2.confidence - 0.08:
                dominant = True

            # Rule 3: Same match priority
            elif p1 == p2:
                # If they matched the same number of tokens:
                if len1 == len2:
                    # c1 is dominant only if confidence gap is >= 0.05
                    if conf_gap >= 0.05:
                        dominant = True
                elif len1 > len2:
                    # c1 matched more tokens, so it dominates if confidence is within 0.08 of c2
                    if conf_gap >= -0.08:
                        dominant = True
                else:
                    # c1 matched fewer tokens than c2, so it needs a large confidence advantage to dominate
                    if conf_gap >= 0.10:
                        dominant = True

            # Rule 4: Priority gap of exactly 1 (e.g. EXACT vs NORMALIZED, NORMALIZED vs SINGULAR_PLURAL)
            elif priority_gap == 1:
                if len1 > len2:
                    if conf_gap >= -0.08:
                        dominant = True
                else:
                    # Dominates if confidence is not worse
                    if conf_gap >= -0.02:
                        dominant = True

            if dominant:
                result_status = ResolutionStatus.WEAK_AMBIGUITY
                dominant_match = c1
            else:
                result_status = ResolutionStatus.STRONG_AMBIGUITY
                dominant_match = None

        # Check if the dominant match has dangerous unmatched tokens
        if result_status in (ResolutionStatus.SINGLE_MATCH, ResolutionStatus.WEAK_AMBIGUITY) and dominant_match:
            unmatched_tokens = [t for t in q_tokens if t not in dominant_match.matched_query_tokens]
            if unmatched_tokens:
                from semantic.matching.singular_plural_matcher import SingularPluralMatcher

                # Candidate's own dimension name, business name, column name, and synonyms are harmless
                cand_dim_names = set()
                if dominant_match.result:
                    res = dominant_match.result
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

                has_dangerous_unmatched = False
                for t in unmatched_tokens:
                    norm_t = SingularPluralMatcher._normalize_text(t)
                    if not norm_t:
                        continue

                    # In simplified contract, any unmatched query token is dangerous unless
                    # it is a stopword or matches the candidate's own dimension metadata.
                    from semantic.matching.stopwords import STOPWORDS
                    if norm_t in STOPWORDS:
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
            dominant_match=dominant_match
        )
