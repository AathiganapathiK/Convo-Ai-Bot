"""
Deterministic scoring and the ambiguity decision for value candidates.

WHY THIS EXISTS

Step 3 made value matching phrase-scoped, which fixed one problem and created
another. Handing the matchers the whole question let unrelated words become
values ("Tell" -> TELLAR). Handing them a bare phrase removed the surrounding
words that had been quietly keeping short values honest: the question "Show
sales for Ramraj brand" never made RAMRAJ PANT a candidate, because "pant" is
not in the question, but the phrase "Ramraj" on its own matches RAMRAJ PANT,
RAMRAJ SHIRT and RAMRAJ DHOTI just as happily as RAMRAJ. One value became a
thirteen-way tie.

So neither signal is sufficient alone, and this module uses both:

  A. the isolated phrase   - what value did the user name?
  B. the original question - is there any evidence for this candidate's
                             EXTRA words, the ones the phrase does not
                             account for?

An extension candidate is only competitive when the question supports the
tokens that make it an extension. That is the whole Ramraj fix, and it is a
statement about evidence rather than a tuned threshold.

WHY NOT A THRESHOLD

A single global fuzzy cutoff cannot separate these cases: RAMRAJ vs RAMRAJ PANT
are similar by construction, and any cutoff that splits them also splits
COIMBATORE from a real misspelling. The signals below are named and additive,
so a decision can be explained by which ones fired.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from semantic.value_provider import ValueCandidate, normalize_for_matching


# Outcome of scoring one phrase.
RESOLVED = "RESOLVED"
AMBIGUOUS = "AMBIGUOUS"
UNRESOLVED = "UNRESOLVED"


# --- weights -----------------------------------------------------------------
# Additive and named. Each corresponds to one piece of evidence, so a score can
# be read back as a sentence rather than tuned as a magic number.

W_EXACT_NORMALIZED = 1.00     # candidate IS the phrase, normalized
W_EXACT_TOKEN_SET = 0.85      # same tokens, different order/punctuation
W_TOKEN_COVERAGE = 0.50       # share of the candidate explained by the phrase
W_PHRASE_COVERAGE = 0.30      # share of the phrase explained by the candidate
W_QUALIFIER = 0.20            # user named this candidate's dimension
W_MATCHER = 0.15              # an existing matcher already vouched for it
W_QUESTION_SUPPORT = 0.45     # the question justifies the candidate's extra words

# A phrase that matches a value almost exactly, end to end, is near-exact
# evidence - not partial coverage. It was previously scored through
# W_TOKEN_COVERAGE, which caps at 0.50 and so could never clear MIN_EVIDENCE
# unless similarity was 0.90+; "Ramrajj" -> RAMRAJ scored 0.43 and failed while
# the legacy path resolved it. Weighted as an exact token-set match discounted
# by similarity, which is what it is.
W_NEAR_SPELLING = 0.85

# Penalty applied to a candidate that strictly extends the phrase when the
# question offers no evidence for the extension. Large on purpose: an
# unsupported extension is a different value, not a near miss.
P_UNSUPPORTED_EXTENSION = 0.60

# A candidate must clear this to be considered evidence at all.
MIN_EVIDENCE = 0.45

# Candidates within this much of the leader are genuinely competitive, and the
# outcome is AMBIGUOUS rather than a coin flip dressed up as an answer.
COMPETITIVE_BAND = 0.15


def _norm(text: str) -> str:
    return normalize_for_matching(text)


def _singular(token: str) -> str:
    """The existing singular form, so plural handling matches the legacy path."""
    from semantic.matching import SingularPluralMatcher
    try:
        return SingularPluralMatcher._to_singular(token)
    except Exception:
        return token


@dataclass
class ScoredCandidate:
    candidate: ValueCandidate
    score: float
    signals: List[str] = field(default_factory=list)

    @property
    def value(self) -> str:
        return self.candidate.value

    @property
    def dimension(self) -> str:
        return self.candidate.dimension


@dataclass
class PhraseResolution:
    """One phrase's outcome. `winner` is set only when status is RESOLVED."""
    phrase: str
    status: str
    scored: List[ScoredCandidate] = field(default_factory=list)
    winner: Optional[ScoredCandidate] = None
    competitive: List[ScoredCandidate] = field(default_factory=list)
    reason: str = ""

    @property
    def values(self) -> List[str]:
        return [s.value for s in self.competitive]


def score_candidate(
    candidate: ValueCandidate,
    phrase: str,
    question: str,
    qualifier_explicit: bool = False,
    phrase_dimension: Optional[str] = None,
    peer_normals: Optional[set] = None,
) -> ScoredCandidate:
    """
    Score one candidate against one phrase, in the context of the question.

    `peer_normals` is the set of normalized values of the other candidates, used
    for signal 8 - whether this candidate is a more specific extension of
    another candidate that is itself an exact match for the phrase.
    """
    signals: List[str] = []
    score = 0.0

    c_norm = _norm(candidate.normalized_value or candidate.value)
    p_norm = _norm(phrase)
    q_norm = _norm(question)

    c_tokens = c_norm.split()
    p_tokens = p_norm.split()
    q_tokens = {_singular(t) for t in q_norm.split()}

    if not c_tokens or not p_tokens:
        return ScoredCandidate(candidate, 0.0, ["empty"])

    # Compare on singular stems, reusing the matcher the legacy path already
    # uses, so "children wear" can reach "N--NIGHT WEARS" the same way it does
    # today. Without this the scorer silently loses every plural match the
    # SingularPluralMatcher exists to catch.
    c_set = {_singular(t) for t in c_tokens}
    p_set = {_singular(t) for t in p_tokens}

    # 1 / 2 - exactness
    if c_norm == p_norm:
        score += W_EXACT_NORMALIZED
        signals.append("exact_normalized")
    elif c_set == p_set:
        score += W_EXACT_TOKEN_SET
        signals.append("exact_token_set")
    else:
        # 3 - similarity, expressed as coverage in both directions so that a
        # long candidate cannot score well on a short phrase by accident.
        overlap = len(c_set & p_set)
        if overlap:
            cov_c = overlap / len(c_set)
            cov_p = overlap / len(p_set)
            score += W_TOKEN_COVERAGE * cov_c + W_PHRASE_COVERAGE * cov_p
            signals.append("token_overlap=%d/%d" % (overlap, len(c_set)))
        else:
            near = _similarity(p_norm, c_norm)
            if near >= 0.80:
                score += W_NEAR_SPELLING * near
                signals.append("near_spelling=%.2f" % near)

    # 4 - the user named this dimension
    if qualifier_explicit and phrase_dimension and \
            candidate.dimension and candidate.dimension.strip().lower() == phrase_dimension.strip().lower():
        score += W_QUALIFIER
        signals.append("dimension_qualified")

    # 7 - an existing matcher already vouched for this candidate
    if candidate.matcher_confidence is not None:
        score += W_MATCHER * float(candidate.matcher_confidence)
        signals.append("matcher=%.2f" % candidate.matcher_confidence)

    # 5 / 6 / 8 / 9 - specificity, containment, and whether the question
    # supports the extra words that make this candidate more specific.
    extra = [t for t in c_tokens if _singular(t) not in p_set]
    if extra and p_set <= c_set:
        signals.append("extension_of_phrase")
        supported = [t for t in extra if _singular(t) in q_tokens]
        if len(supported) == len(extra):
            score += W_QUESTION_SUPPORT
            signals.append("question_supports_extension")
        else:
            extends_exact_peer = bool(peer_normals and p_norm in peer_normals)
            if extends_exact_peer:
                score -= P_UNSUPPORTED_EXTENSION
                signals.append("unsupported_extension_of_exact_peer")
            else:
                score -= P_UNSUPPORTED_EXTENSION / 2.0
                signals.append("unsupported_extension")

    return ScoredCandidate(candidate, round(max(0.0, score), 4), signals)


def resolve_phrase(
    candidates: List[ValueCandidate],
    phrase: str,
    question: str,
    qualifier_explicit: bool = False,
    phrase_dimension: Optional[str] = None,
) -> PhraseResolution:
    """
    Score every candidate for one phrase and decide RESOLVED/AMBIGUOUS/UNRESOLVED.

    The decision is by evidence margin, never by candidate count: two candidates
    are not automatically ambiguous, and ten are not automatically unresolvable.
    """
    if not phrase or not str(phrase).strip():
        return PhraseResolution(phrase=phrase or "", status=UNRESOLVED,
                                reason="empty phrase")

    if not candidates:
        return PhraseResolution(phrase=phrase, status=UNRESOLVED,
                                reason="no candidate values from the provider")

    # Deduplicate on (dimension, normalized value): the same value indexed twice
    # is one candidate, and must not look like corroboration.
    seen = set()
    unique: List[ValueCandidate] = []
    for c in candidates:
        key = ((c.dimension or "").lower(), _norm(c.normalized_value or c.value))
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)

    peer_normals = {_norm(c.normalized_value or c.value) for c in unique}

    scored = [
        score_candidate(c, phrase, question, qualifier_explicit,
                        phrase_dimension, peer_normals)
        for c in unique
    ]
    scored.sort(key=lambda s: (-s.score, s.value))

    viable = [s for s in scored if s.score >= MIN_EVIDENCE]
    if not viable:
        return PhraseResolution(phrase=phrase, status=UNRESOLVED, scored=scored,
                                reason="no candidate reached the evidence floor")

    top = viable[0]
    competitive = [s for s in viable if top.score - s.score <= COMPETITIVE_BAND]

    if len(competitive) == 1:
        # Family ambiguity. An exact match beats its own extensions on score,
        # and rightly so - but "Show sales for Ramraj", with RAMRAJ PANT and
        # RAMRAJ SHIRT also configured, genuinely does not say whether the user
        # means the RAMRAJ line or the RAMRAJ family. Scoring cannot settle
        # that, because the missing information is in the user's head, not in
        # the evidence. Naming the dimension ("Ramraj brand") does settle it,
        # so an explicit qualifier keeps the resolution.
        # Same dimension only. RAMRAJ / RAMRAJ PANT are one brand family and
        # the user may have meant either. SHIRT (a Product) and RAMRAJ SHIRT
        # (a Brand) merely share a word - that is not a family, and treating it
        # as one would make every exact match ambiguous with every longer value
        # anywhere in the configuration.
        family = [
            s for s in scored
            if "unsupported_extension_of_exact_peer" in s.signals
            and (s.dimension or "").strip().lower() == (top.dimension or "").strip().lower()
        ]
        if family and not qualifier_explicit and "exact_normalized" in top.signals:
            return PhraseResolution(
                phrase=phrase, status=AMBIGUOUS, scored=scored,
                competitive=[top] + family,
                reason=(
                    "'%s' matches a value exactly, but %d more specific value(s) "
                    "share it and the question does not say which was meant"
                    % (phrase, len(family))
                ),
            )

        return PhraseResolution(
            phrase=phrase, status=RESOLVED, scored=scored,
            winner=top, competitive=competitive,
            reason="one candidate dominates (%s)" % ", ".join(top.signals),
        )

    return PhraseResolution(
        phrase=phrase, status=AMBIGUOUS, scored=scored, competitive=competitive,
        reason="%d candidates within the competitive band" % len(competitive),
    )


def to_match_results(resolution: PhraseResolution, phrase: Optional[str] = None):
    """
    Compatibility adapter: scorer decision -> existing MatchResult objects.

    This is the whole integration. The scorer decides WHICH candidates survive;
    everything after this - consolidation, containment, competition, the
    ambiguity classifier, reachability - is the existing engine, unchanged and
    unduplicated. There is deliberately no second ambiguity engine here.

    Emission follows the scorer's status directly:

        RESOLVED    -> one MatchResult, the winner
        AMBIGUOUS   -> one per competitive candidate, so the existing
                       ambiguity classifier sees a real tie and reports it
        UNRESOLVED  -> nothing, so the existing unresolved-value handling
                       (Gate 3 Step 21a) fires exactly as it does today

    WHAT WOULD BE LOST, AND WHERE IT GOES INSTEAD

    MatchResult is frozen and has no field for a score, the signals that
    produced it, or candidate provenance. Rather than distort existing fields
    to carry them, provenance and signals are written into `reason` (free text,
    already used for exactly this by every matcher), and the full
    PhraseResolution objects are kept beside the matches by the caller. No
    scorer information is destroyed by this conversion.

    Both token fields are set to the PHRASE's tokens, never the question's.
    That is what keeps multiple phrases independent downstream: the competition
    logic reads matched_question_tokens_precise to decide what competes with
    what, so a Chennai candidate and a Ramraj candidate can never share a token
    and be bridged into one false ambiguity.
    """
    from semantic.matching import MatchResult, MatchType

    if resolution.status == UNRESOLVED:
        return []

    if resolution.status == RESOLVED and resolution.winner is not None:
        emit = [resolution.winner]
    else:
        emit = list(resolution.competitive)

    phrase_tokens = _norm(phrase if phrase is not None else resolution.phrase).split()

    out = []
    for scored in emit:
        candidate = scored.candidate

        if "exact_normalized" in scored.signals:
            match_type = MatchType.EXACT
        elif "exact_token_set" in scored.signals:
            match_type = MatchType.NORMALIZED
        else:
            match_type = MatchType.FUZZY

        value_norm = _norm(candidate.normalized_value or candidate.value)

        out.append(
            MatchResult(
                matched=True,
                value=candidate.value,
                normalized_value=value_norm,
                confidence=min(1.0, round(scored.score, 4)),
                match_type=match_type,
                reason="candidate-scoped score=%.2f [%s] provenance=%s" % (
                    scored.score, ", ".join(scored.signals) or "none",
                    candidate.provenance,
                ),
                matched_question_tokens=list(phrase_tokens),
                matched_value_tokens=value_norm.split(),
                dimension_id=candidate.dimension_id,
                business_name=candidate.dimension,
                table_name=candidate.table_name,
                column_name=candidate.column_name,
                matched_question_tokens_precise=list(phrase_tokens),
            )
        )

    return out


def _similarity(a: str, b: str) -> float:
    """
    Character-level similarity for near spellings, without a new dependency.

    Only ever used to keep a misspelling alive ("coimbator" -> COIMBATORE); it
    can never on its own carry a candidate past a candidate that matched
    exactly.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    matched = 0
    i = 0
    for ch in longer:
        if i < len(shorter) and shorter[i] == ch:
            matched += 1
            i += 1
    return matched / len(longer)
