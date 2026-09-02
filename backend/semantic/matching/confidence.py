"""
Gate 3 Step 21b - evidence-based confidence.

WHAT WAS WRONG

MatchConfidence used to be the whole story:

    EXACT = 1.00   NORMALIZED = 0.98   SINGULAR_PLURAL = 0.95   FUZZY = 0.90

That is a record of WHICH MATCHER FIRED, not of how strong the evidence is. Two
exact matches therefore always had a confidence gap of exactly 0.00, and the
dominance rules in models.py - four rules built on eight hand-tuned thresholds -
could never separate them. "Show sales for VT division" returned
STRONG_AMBIGUITY not because the question was ambiguous but because the model
had nothing to compare.

WHAT REPLACES IT

Six independent signals, each in [0, 1], each computed from data the request
already holds, each recorded so a decision can be explained to an
administrator rather than asserted:

    tier            how the match was made (this is the old constant, kept as
                    ONE signal instead of the entire score)
    query_coverage  share of the question's entity tokens this candidate explains
    value_coverage  share of the STORED VALUE the match explains
    specificity     inverse of how many candidates share the same evidence
    config_trust    what the administrator has said about this dimension
    table_affinity  whether the candidate sits on the resolved metric's table

value_coverage is the signal that did not exist before and it is the one that
does most of the work. "RAMRAJ" against the stored value "RAMRAJ DHOTI" explains
one of two tokens, so it scores 0.5; "BANIANS" against "BANIANS" scores 1.0.
That single number separates a precise hit from a prefix hit, which is what the
RAMRAJ family, "Banianist" -> BANIANS and "city" -> ELECTRONIC CITY all turn on.

WHY A VECTOR AND NOT JUST A NUMBER

Replacing eight magic thresholds with six magic weights would be no improvement.
The vector is kept so that models.py can ask the parameter-free question first:
does one candidate beat another on EVERY signal? That is Pareto dominance and it
needs no tuning at all. Only when candidates genuinely trade off - better here,
worse there - does the scalar below arbitrate, against a single margin. Eight
tunable numbers become one.

The scalar is a ranking device, not a probability. It is not calibrated to mean
"75% likely correct" and must not be reported as though it were.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence


class MatchConfidence:
    """
    Per-matcher priors. Retained because the matchers still stamp these onto
    MatchResult.confidence at match time, and because the tier signal below is
    derived from them. They are no longer the whole confidence.
    """
    EXACT = 1.00
    NORMALIZED = 0.98
    SINGULAR_PLURAL = 0.95
    FUZZY = 0.90


class MatchSettings:
    FUZZY_SCORE_CUTOFF = 85
    MAX_CANDIDATE_NGRAM = 3


# How much each signal contributes to the scalar tie-breaker. These matter only
# when Pareto dominance is inconclusive, which is why there are six of them
# rather than eight thresholds: they order candidates, they do not gate them.
#
# value_coverage and query_coverage carry the most weight because they are the
# only two signals that measure how much of the actual question and the actual
# stored value were explained. tier follows: how a match was made is real
# evidence but weaker than how much it accounted for. The remaining three are
# corroborating context.
WEIGHTS = {
    "value_coverage": 0.30,
    "query_coverage": 0.25,
    "tier": 0.20,
    "specificity": 0.10,
    "config_trust": 0.10,
    "table_affinity": 0.05,
}

# The one remaining tunable number. Two candidates whose scalars differ by less
# than this are treated as genuinely ambiguous. Calibrated against the Step 16
# VALID cases - the set independently verified as both correct expectation and
# correct behaviour - and deliberately not fitted to the failing cases.
DOMINANCE_MARGIN = 0.08

# Tier values. EXACT is certain about the method; FUZZY is modulated by its own
# similarity score so a 0.86 fuzzy hit does not look like a 0.99 one.
_TIER = {
    "EXACT": 1.00,
    "NORMALIZED": 0.90,
    "SINGULAR_PLURAL": 0.80,
}
# Fuzzy sits below every other tier because it is weaker evidence than any of
# them, and inside that band a similarity difference is preserved ONE FOR ONE.
# Stretching the accepted band (0.85..1.0) across a wider tier range would
# amplify a 0.04 similarity difference into something that looks decisive; a
# 4% fuzzy difference between two different values is noise, not evidence.
_FUZZY_TIER_FLOOR = 0.40

# "Strictly better" for Pareto purposes. Without it any epsilon on a single
# axis would count as dominance, and two near-identical fuzzy candidates would
# pick a winner they have not earned.
PARETO_EPSILON = 0.05


@dataclass(frozen=True)
class EvidenceScore:
    """One candidate's evidence, decomposed. Every field is in [0, 1]."""

    tier: float
    query_coverage: float
    value_coverage: float
    specificity: float
    config_trust: float
    table_affinity: float
    scalar: float

    def vector(self) -> tuple:
        """The components, for Pareto comparison. Order is not significant."""
        return (
            self.tier,
            self.query_coverage,
            self.value_coverage,
            self.specificity,
            self.config_trust,
            self.table_affinity,
        )

    def dominates(self, other: "EvidenceScore") -> bool:
        """
        Pareto dominance: at least as good on every signal, strictly better on
        one. Parameter-free, so it needs no calibration and cannot drift.
        """
        mine, theirs = self.vector(), other.vector()
        return all(a >= b - 1e-9 for a, b in zip(mine, theirs)) and any(
            a > b + PARETO_EPSILON for a, b in zip(mine, theirs)
        )

    def explain(self) -> str:
        return (
            "tier=%.2f query_cov=%.2f value_cov=%.2f spec=%.2f "
            "config=%.2f table=%.2f -> %.3f"
            % (self.tier, self.query_coverage, self.value_coverage,
               self.specificity, self.config_trust, self.table_affinity,
               self.scalar)
        )


def _singular(token: str) -> str:
    """
    Reduce a token to its singular so coverage is measured on meaning rather
    than surface form. Without this "pant" and "pants" never intersect, and a
    plural question scores zero coverage against every singular value it should
    match - which is exactly the case SingularPluralMatcher exists to handle.
    """
    try:
        from semantic.matching.singular_plural_matcher import SingularPluralMatcher
        return SingularPluralMatcher._to_singular(token)
    except Exception:
        return token[:-1] if token.endswith("s") and len(token) > 3 else token


def _norm_tokens(text: Optional[str]) -> List[str]:
    return [t for t in (text or "").lower().replace(",", " ").split() if t]


def _singular_set(tokens) -> set:
    return {_singular(t.lower()) for t in (tokens or []) if t}


def _tier_score(match_type_name: str, raw_confidence: float) -> float:
    if match_type_name in _TIER:
        return _TIER[match_type_name]

    # FUZZY. Spread the accepted band (cutoff..1.0) across a range that keeps
    # every fuzzy hit below every exact one, because it should be.
    cutoff = MatchSettings.FUZZY_SCORE_CUTOFF / 100.0
    if raw_confidence <= cutoff:
        return _FUZZY_TIER_FLOOR
    return _FUZZY_TIER_FLOOR + (raw_confidence - cutoff)


def _config_trust(dimension_meta: Optional[dict]) -> float:
    """
    What the administrator has said about this dimension.

    A confirmed dimension is one a person reviewed and approved, which is the
    strongest non-lexical evidence available. GROUPING is the role meant for
    business breakdowns; IDENTIFIER is a key and is a weaker filter target.
    Absent configuration scores in the middle rather than badly - an unreviewed
    dimension is unknown, not wrong.
    """
    if not dimension_meta:
        return 0.5

    score = 0.5

    if dimension_meta.get("is_confirmed"):
        score += 0.3

    role = (dimension_meta.get("dimension_role") or "").upper()
    if role == "GROUPING":
        score += 0.2
    elif role == "IDENTIFIER":
        score -= 0.2
    elif role == "TIME_LABEL":
        score += 0.1

    return max(0.0, min(1.0, score))


def score_candidates(
    choices: Sequence,
    entity_tokens: Sequence[str],
    dimension_meta: Optional[Dict] = None,
    metric_tables: Optional[Sequence[str]] = None,
) -> List[EvidenceScore]:
    """
    Score every candidate against the others.

    Pure: depends only on its arguments, holds no state and caches nothing, so
    it is safe under concurrent requests by construction.

    `dimension_meta` maps a dimension id to {is_confirmed, dimension_role}.
    `metric_tables` are the tables the question's metrics resolved to.
    Both are optional; absent, their signals fall back to neutral and the
    remaining four still separate candidates.
    """
    dimension_meta = dimension_meta or {}
    metric_tables = {t for t in (metric_tables or []) if t}

    entity_token_set = _singular_set(entity_tokens)

    def _claim_key(choice) -> tuple:
        """
        The identity a value claim is counted under.

        Gate 3 Step 21f. This used to be the bare normalized value, which
        counted two candidates as competing duplicates whenever they merely
        shared a string - regardless of whether they were even on the same
        column. City=COIMBATORE and District=COIMBATORE are two different,
        genuinely true facts about this data (Coimbatore is both a city and a
        district), and VT is a real Division value on three separate tables.
        Each of those is the ONLY claimant of that value within its own
        physical column, yet each was scoring 0.50 or 0.33 specificity purely
        because the others existed - while an unrelated accidental match with
        a unique string kept the full 1.00.

        Including the physical column keeps the signal's original intent - a
        value many candidates claim is weaker evidence than one only a single
        candidate offers - and scopes "many candidates" to what actually
        competes: the same value on the same table and column. Nothing is
        deduplicated or removed; every candidate is still scored.
        """
        res = getattr(choice, "result", choice)
        return (
            (getattr(res, "table_name", None) or "").lower(),
            (getattr(res, "column_name", None) or "").lower(),
            (getattr(choice, "normalized_value", None) or "").lower(),
        )

    # Specificity: how many candidates claim the same stored value on the same
    # column. A value that only one candidate offers is better evidence than
    # one eight offer.
    value_claims: Dict[tuple, int] = {}
    for choice in choices:
        key = _claim_key(choice)
        value_claims[key] = value_claims.get(key, 0) + 1

    scores: List[EvidenceScore] = []

    for choice in choices:
        result = getattr(choice, "result", choice)

        match_type = getattr(result, "match_type", None)
        match_type_name = getattr(match_type, "value", str(match_type or ""))
        raw_confidence = float(getattr(result, "confidence", 0.0) or 0.0)

        tier = _tier_score(match_type_name, raw_confidence)

        # Query coverage: how much of the question this candidate's own value
        # accounts for. Measured against the value's tokens rather than the
        # matcher's reported question tokens, because several matchers report
        # the whole question span regardless of how much of it they explain -
        # "LINEN PANT" and "COTTON PANT" both claim the span "cotton pant"
        # while only one of them accounts for both words.
        matched_v_tokens = _singular_set(
            getattr(result, "matched_value_tokens", None)
        )
        matched_q = _singular_set(
            getattr(result, "matched_question_tokens", None)
        )
        if match_type_name == "FUZZY":
            # Gate 3 Step 21f. For every other tier the value's own tokens ARE
            # the question's tokens - "chennai" matched "CHENNAI" - so
            # measuring coverage against the value works, and it is what keeps
            # "LINEN PANT" from claiming credit for "cotton". A fuzzy match is
            # precisely the case where the two differ by spelling: the stored
            # value is "coimbatore" and the question said "coimbator", so the
            # intersection is guaranteed empty and a correct match scored 0.00
            # coverage while an accidental one scored 0.50.
            #
            # The value tokens therefore stay PRIMARY, and only the token
            # FuzzyMatcher actually approved for THIS candidate
            # (matched_question_tokens_precise) is unioned in. The span it
            # searched with (matched_question_tokens) is deliberately not used:
            # both "COTTON PANT" and "LINEN PANT" report the whole "cotton
            # pant" span, so using it would hand each of them the other's
            # evidence and collapse a real dominance decision.
            #
            # A fuzzy candidate whose precise evidence is absent gains
            # nothing, and EXACT/NORMALIZED/SINGULAR_PLURAL keep the original
            # expression below, unchanged.
            precise_q = _singular_set(
                getattr(result, "matched_question_tokens_precise", None)
            )
            evidence_tokens = matched_v_tokens | precise_q
        else:
            evidence_tokens = matched_v_tokens or matched_q
        if entity_token_set:
            query_coverage = (
                len(evidence_tokens & entity_token_set) / len(entity_token_set)
            )
        else:
            query_coverage = 1.0 if evidence_tokens else 0.0

        # Value coverage: of the stored value, how much did the match explain.
        # This is the signal that separates a precise hit from a prefix hit.
        value_tokens = [_singular(t) for t in _norm_tokens(getattr(result, "value", ""))]
        matched_v = matched_v_tokens
        if value_tokens:
            covered = len({t for t in value_tokens if t in matched_v})
            value_coverage = covered / len(value_tokens)
            if not matched_v:
                # Some matchers do not report value tokens. Fall back to a
                # length ratio rather than scoring a real match as zero.
                matched_text = " ".join(matched_q)
                value_coverage = min(
                    1.0,
                    len(matched_text) / max(len(" ".join(value_tokens)), 1),
                )
        else:
            value_coverage = 0.0

        specificity = 1.0 / value_claims.get(_claim_key(choice), 1)

        config_trust = _config_trust(
            dimension_meta.get(getattr(result, "dimension_id", None))
        )

        table_name = getattr(result, "table_name", None)
        if not metric_tables:
            table_affinity = 0.5
        else:
            table_affinity = 1.0 if table_name in metric_tables else 0.0

        parts = {
            "tier": tier,
            "query_coverage": query_coverage,
            "value_coverage": value_coverage,
            "specificity": specificity,
            "config_trust": config_trust,
            "table_affinity": table_affinity,
        }
        scalar = sum(WEIGHTS[name] * value for name, value in parts.items())

        scores.append(EvidenceScore(scalar=round(scalar, 6), **parts))

    return scores
