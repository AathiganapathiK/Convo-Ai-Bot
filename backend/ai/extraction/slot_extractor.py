"""
Gate 4 Steps 25, 26, 27 - one structured extraction, then deterministic review.

THE SHAPE OF THIS MODULE

    deterministic read  ->  one LLM call  ->  reconcile  ->  escalate if needed

The deterministic read comes first and is not a fallback. Counting "top 5",
recognising that "reducing" describes motion, and checking a term against the
configured vocabulary are all things code does exactly and a model does
approximately. The model is asked for the part that genuinely needs language
understanding - which of several readings the sentence supports - and its answer
is then checked against what the deterministic pass already knows.

WHERE THE TWO DISAGREE

Disagreement is the most informative signal available here, and it is treated
that way rather than resolved by precedence. When the deterministic pass and the
model differ on a field, that field is marked low-confidence and escalated to
the stronger model (step 26). It is never silently resolved in favour of either,
because both are capable of being wrong in this exact situation: the regex
misses an unusual phrasing, the model over-reads a stray word.

The one exception is fabrication. A metric or dimension the model returned that
does not exist in the configured vocabulary is dropped outright, not escalated.
There is nothing for a stronger model to adjudicate: the field is not in the
semantic layer, so no reading of the question can make it valid.

WHEN NO MODEL IS AVAILABLE

The extractor returns the deterministic reading with tier UNAVAILABLE rather
than raising. A question whose ranking structure is fully determined by its
wording - which the canonical case is - still extracts correctly with no model
at all, and the pipeline degrades to Gate 1 behaviour rather than failing.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ai.extraction.models import (
    CLARIFY_CONFIDENCE,
    Clarification,
    EscalationTier,
    ExtractedIntent,
    LOW_CONFIDENCE,
    MAX_VALUE_PHRASES,
    SlotName,
    ValuePhrase,
    coerce_confidence,
    coerce_enum,
    coerce_top_n,
)
from ai.extraction.prompts import build_escalation_prompt, build_extraction_prompt
from semantic.models.semantic_plan import (
    AnalysisMode,
    RankDirection,
    RankMeasure,
)

logger = logging.getLogger(__name__)


# Purposes looked up through FallbackService. "extraction" is the fast model;
# "extraction_escalation" is the stronger one. Both are ordinary purposes an
# administrator configures in the AI Control Center - no new routing mechanism.
PRIMARY_PURPOSE = "extraction"
ESCALATION_PURPOSE = "extraction_escalation"

# When "extraction" has no configured models, fall back to the purpose that is
# always configured, because an unconfigured purpose must not disable the gate.
FALLBACK_PURPOSE = "sql_generation"


# ---------------------------------------------------------------------------
# Deterministic signals
# ---------------------------------------------------------------------------
# Every pattern is whole-word anchored. Substring matching is what previously
# made "stopped" a ranking question because it contains "top", and the same
# mistake here would put a top_n on a question that has no ranking at all.

_TOP_N_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20, "fifty": 50,
}

_RANK_HEAD = r"(?:top|bottom|first|last|best|worst|highest|lowest)"

# "last two quarters" is a period, not a ranking of two things - and the same
# head word carries both meanings, so the count alone cannot tell them apart.
# What separates them is the noun: a count followed by a time unit is duration.
# Only the temporal-capable heads are guarded, so "top 5 months by sales" - a
# genuine ranking whose items happen to be months - still reads as a ranking.
_TEMPORAL_HEAD = r"(?:last|first|past|next|previous|prior|coming|recent)"
_TIME_UNIT = r"(?:year|quarter|month|week|day|hour|fortnight|decade)s?"

_TOP_N_NUMERIC = re.compile(rf"\b{_RANK_HEAD}\s+(\d{{1,4}})\b", re.IGNORECASE)
_TOP_N_WORD = re.compile(
    rf"\b{_RANK_HEAD}\s+({'|'.join(_TOP_N_WORDS)})\b", re.IGNORECASE
)

_DURATION_PHRASE = re.compile(
    rf"\b{_TEMPORAL_HEAD}\s+(?:\d{{1,4}}|{'|'.join(_TOP_N_WORDS)})\s+{_TIME_UNIT}\b",
    re.IGNORECASE,
)

# "fastest", "sharpest" and "steepest" are included because they are ordering
# words in their own right - "fastest declining brands" is a ranking even though
# it contains no top/bottom head. Bare motion words like "declining" are NOT
# here on purpose: "sales are declining" is a descriptive statement, not a
# request for an ordered list, and admitting it would put a ranking on it.
_RANKING_CUES = re.compile(
    r"\b(top|bottom|highest|lowest|best|worst|rank|ranks|ranked|ranking|"
    r"least|most|leading|trailing|fastest|sharpest|steepest|quickest)\b",
    re.IGNORECASE,
)

_ASC_CUES = re.compile(
    r"\b(bottom|lowest|worst|least|smallest|fewest|poorest|"
    r"reducing|reduced|declining|declined|decreasing|decreased|falling|fell|"
    r"dropping|dropped|shrinking|shrank|losing|lost|down|worsening|worsened)\b",
    re.IGNORECASE,
)

_DESC_CUES = re.compile(
    r"\b(top|highest|best|most|biggest|largest|greatest|leading|"
    r"growing|grew|rising|rose|increasing|increased|improving|improved|"
    r"gaining|gained|up)\b",
    re.IGNORECASE,
)

# Words describing MOTION of a measure. Their presence is what makes a ranking
# order on the change rather than on the level - the distinction the canonical
# case turns on.
_CHANGE_CUES = re.compile(
    r"\b(reducing|reduced|reduce|declining|declined|decline|decreasing|"
    r"decreased|decrease|falling|fell|fall|dropping|dropped|drop|"
    r"shrinking|shrank|shrink|growing|grew|grow|growth|rising|rose|rise|"
    r"increasing|increased|increase|improving|improved|improve|"
    r"worsening|worsened|worsen|gaining|gained|losing|lost|"
    r"trending|movement|moved|change|changed|changing|swing)\b",
    re.IGNORECASE,
)

# Percentage framing turns CHANGE into CHANGE_PCT.
_PCT_CUES = re.compile(
    r"(%|\bpercent\b|\bpercentage\b|\bpct\b|\bfastest\b|\bsharpest\b|\brate of\b)",
    re.IGNORECASE,
)

# Words describing SIZE. These order on the level, not the movement.
_ABSOLUTE_CUES = re.compile(
    r"\b(biggest|largest|smallest|highest|lowest|greatest|most|least|"
    r"by\s+(?:sales|revenue|value|amount|quantity|volume))\b",
    re.IGNORECASE,
)

_TREND_CUES = re.compile(
    r"\b(trend|trends|trending)\b|\bover\s+time\b|\bmonth\s+by\s+month\b|"
    r"\b(monthly|weekly|daily|quarterly|yearly)\b",
    re.IGNORECASE,
)

_COMPARISON_CUES = re.compile(
    r"\b(compare|compares|compared|comparison|versus|vs|against)\b",
    re.IGNORECASE,
)

_DIAGNOSTIC_CUES = re.compile(
    r"\b(why|reason|reasons|cause|caused|causes|because|explain|"
    r"root\s+cause|driver|drivers|drove|attributable)\b",
    re.IGNORECASE,
)

_PRESCRIPTIVE_CUES = re.compile(
    r"\b(should|recommend|recommendation|recommendations|suggest|suggestion|"
    r"how\s+(?:do|can|should)\s+(?:i|we)|what\s+(?:do|can|should)\s+(?:i|we)|"
    r"improve|increase\s+our|fix|action|advise)\b",
    re.IGNORECASE,
)


# Period wording. This records WHAT THE USER SAID, not what it resolves to -
# turning "last quarter" into dates is semantic/temporal's job and it is far
# better at it than a regex would be. All that is needed here is to know a
# period was stated, so that step 28 does not ask for one the user gave.
_PERIOD_PHRASE = re.compile(
    r"\b("
    r"(?:last|this|previous|prior|past|current|next|coming)\s+"
    r"(?:year|quarter|month|week|day|fortnight|"
    r"(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|twelve)\s+"
    r"(?:years?|quarters?|months?|weeks?|days?))|"
    r"(?:year|month|quarter)\s+to\s+date|ytd|mtd|qtd|"
    r"today|yesterday|so\s+far\s+this\s+(?:year|month|quarter|week)|"
    r"(?:in|for|during|since)\s+(?:19|20)\d{2}|(?:19|20)\d{2}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
    r"(?:uary|ruary|ch|il|e|y|ust|tember|ober|ember)?"
    r")\b",
    re.IGNORECASE,
)

# A second period the first is measured against.
_COMPARISON_PHRASE = re.compile(
    r"\b(?:versus|vs\.?|compared\s+(?:to|with)|against|"
    r"(?:year|month|quarter)\s+on\s+(?:year|month|quarter)|yoy|mom|qoq)"
    r"(?:\s+((?:the\s+)?[a-z0-9]+(?:\s+[a-z0-9]+){0,2}))?",
    re.IGNORECASE,
)


def _deterministic_period(question: str) -> Optional[str]:
    """The user's own period wording, verbatim, or None."""
    match = _PERIOD_PHRASE.search(question)
    return match.group(1).strip() if match else None


def _deterministic_comparison(question: str) -> Optional[str]:
    """
    The comparison period, when the question names one.

    Returns the whole matched phrase rather than the trailing capture, so that
    "vs last year" is recorded as written instead of as a bare "last year" that
    reads like the primary period.
    """
    match = _COMPARISON_PHRASE.search(question)
    if not match:
        return None
    phrase = match.group(0).strip()
    return phrase or None


def _deterministic_top_n(question: str) -> Optional[int]:
    """
    A row count, or None.

    Duration phrases are removed before the count patterns run, so "sales for
    the last two quarters over the top 5 brands" still finds 5 and never 2.
    """
    text = _DURATION_PHRASE.sub(" ", question)

    match = _TOP_N_NUMERIC.search(text)
    if match:
        return coerce_top_n(match.group(1))

    match = _TOP_N_WORD.search(text)
    if match:
        return _TOP_N_WORDS.get(match.group(1).lower())

    return None


def _deterministic_measure(question: str) -> Optional[RankMeasure]:
    """
    Whether a ranking orders on the level or on the movement.

    Motion wins over size when both appear. "Top 5 products whose sales are
    reducing" contains "top", a size-ish word, and "reducing", a motion word -
    but the motion word is what the ordering is actually about. Reading it the
    other way answers a different question, which is the specific bug this gate
    was opened to fix.
    """
    if not _CHANGE_CUES.search(question):
        return RankMeasure.ABSOLUTE if _ABSOLUTE_CUES.search(question) else None

    if _PCT_CUES.search(question):
        return RankMeasure.CHANGE_PCT

    return RankMeasure.CHANGE


def _deterministic_direction(question: str, measure: Optional[RankMeasure]) -> Optional[RankDirection]:
    """
    Ordering direction, read against whatever the measure turned out to be.

    With measure=CHANGE the direction describes the change: "reducing" means
    the most negative first, which is ASC even though the sentence opens with
    "Top". The head word "top" is about how many, not which end.
    """
    if measure in (RankMeasure.CHANGE, RankMeasure.CHANGE_PCT):
        # Direction follows the motion word, not the "top"/"bottom" head.
        if _ASC_CUES.search(question):
            return RankDirection.ASC
        if _DESC_CUES.search(question):
            return RankDirection.DESC
        return None

    has_asc = bool(_ASC_CUES.search(question))
    has_desc = bool(_DESC_CUES.search(question))

    if has_asc and not has_desc:
        return RankDirection.ASC
    if has_desc and not has_asc:
        return RankDirection.DESC

    # Both or neither. "Top 5 worst" is contradictory and must not be guessed;
    # step 26 will treat the absence as unresolved rather than picking one.
    return None


def _deterministic_mode(question: str, top_n: Optional[int]) -> Optional[AnalysisMode]:
    """
    Mode from wording alone.

    Order matters. A diagnostic question that also says "top" is still
    diagnostic - "why are our top brands falling" is asking why - so the
    intent-bearing cues are tested before the shape-bearing ones.
    """
    if _PRESCRIPTIVE_CUES.search(question):
        return AnalysisMode.PRESCRIPTIVE
    if _DIAGNOSTIC_CUES.search(question):
        return AnalysisMode.DIAGNOSTIC
    if top_n is not None or _RANKING_CUES.search(question):
        return AnalysisMode.RANKING
    if _TREND_CUES.search(question):
        return AnalysisMode.TREND
    if _COMPARISON_CUES.search(question):
        return AnalysisMode.COMPARISON
    return None


def read_deterministic_signals(question: str) -> ExtractedIntent:
    """
    Everything derivable from the wording without a model.

    Confidence here is high but not 1.0. These patterns are exact about what
    they match and silent about what they miss, so a hit is strong evidence -
    but "top" inside an unusual construction is still possible, and reserving
    the last sliver keeps the escalation path reachable.
    """
    intent = ExtractedIntent(escalation_tier=EscalationTier.DETERMINISTIC)
    question = question or ""

    top_n = _deterministic_top_n(question)
    mode = _deterministic_mode(question, top_n)

    if mode is not None:
        intent.mode = mode
        intent.confidence[SlotName.MODE.value] = 0.90

    if mode == AnalysisMode.RANKING:
        measure = _deterministic_measure(question)
        direction = _deterministic_direction(question, measure)

        if top_n is not None:
            intent.top_n = top_n
            intent.confidence[SlotName.TOP_N.value] = 0.98
        if measure is not None:
            intent.measure = measure
            intent.confidence[SlotName.MEASURE.value] = 0.88
        if direction is not None:
            intent.direction = direction
            intent.confidence[SlotName.DIRECTION.value] = 0.88

    period = _deterministic_period(question)
    if period is not None:
        intent.time_period = period
        intent.evidence[SlotName.TIME_PERIOD.value] = period
        # Lower than the structural slots on purpose. The pattern proves a
        # period was mentioned; it does not prove it is the period the question
        # is *about* ("sales in 2024 branches"), so the model gets a say.
        intent.confidence[SlotName.TIME_PERIOD.value] = 0.80

    comparison = _deterministic_comparison(question)
    if comparison is not None:
        intent.comparison_period = comparison
        intent.evidence[SlotName.COMPARISON.value] = comparison
        intent.confidence[SlotName.COMPARISON.value] = 0.80

    if mode in (AnalysisMode.DIAGNOSTIC, AnalysisMode.PRESCRIPTIVE):
        intent.unsupported.append(mode.value)

    return intent


# ---------------------------------------------------------------------------
# Model output parsing
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> Optional[dict]:
    """
    The first JSON object in a model response.

    Models fence their JSON, prefix it with "Here is", or append a sentence of
    explanation despite being told not to. Rather than trusting the instruction,
    the first balanced brace span is located and parsed. A response with no
    parseable object returns None and is treated as an unavailable extraction,
    never as an empty one - "the model said nothing" and "the model said there
    is nothing" are different and must not collapse.
    """
    if not raw:
        return None

    text = raw.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]

        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:index + 1])
                except json.JSONDecodeError:
                    return None

    return None


def _response_text(response: Any) -> str:
    """Content of a provider response, tolerating every shape seen so far."""
    if not response:
        return ""
    choices = getattr(response, "choices", None)
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if not message:
        return ""
    return getattr(message, "content", None) or ""


def _call_model(purpose: str, prompt: str, company_id: Optional[str]) -> Optional[str]:
    """
    One model call. Returns None on any failure.

    Failure is swallowed on purpose. Extraction is an enrichment: without it the
    plan builder falls through to the Gate 1 heuristics that shipped before this
    gate existed. Letting a provider outage raise here would take down the chat
    feature to protect an optimisation.
    """
    from services.llm_execution_service import LLMExecutionService

    try:
        response = LLMExecutionService.execute(
            purpose=purpose,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            company_id=company_id,
        )
        return _response_text(response)
    except Exception as exc:
        logger.warning(
            "Extraction call failed for purpose=%s (%s).",
            purpose,
            str(exc).splitlines()[0][:200],
        )
        return None


def _call_with_fallback(purpose: str, prompt: str, company_id: Optional[str]) -> Optional[str]:
    """
    Try the intended purpose, then the purpose that is certain to be configured.

    A deployment that has not registered an "extraction" model should still get
    extraction rather than silently losing the whole gate.
    """
    raw = _call_model(purpose, prompt, company_id)
    if raw:
        return raw
    if purpose != FALLBACK_PURPOSE:
        logger.info("Purpose %s unavailable; retrying on %s.", purpose, FALLBACK_PURPOSE)
        return _call_model(FALLBACK_PURPOSE, prompt, company_id)
    return None


# ---------------------------------------------------------------------------
# Validation against the semantic layer
# ---------------------------------------------------------------------------

def _validate_terms(
    raw_terms: Any,
    configured: List[str],
    kind: str,
    notes: List[str],
) -> List[str]:
    """
    Keep only terms that exist in the configured vocabulary.

    Case-insensitive match against the configured business names, returning the
    configured spelling rather than the model's. Anything unmatched is dropped
    with a note. This is the single hard rule of the gate: a metric or dimension
    that is not configured cannot enter the plan, no matter how confident the
    model was, because there is no column behind it.
    """
    if not isinstance(raw_terms, list):
        return []

    lookup = {str(name).strip().lower(): str(name) for name in configured if name}
    kept: List[str] = []

    for term in raw_terms:
        if not isinstance(term, str):
            continue
        candidate = term.strip()
        if not candidate:
            continue

        matched = lookup.get(candidate.lower())
        if matched is None:
            notes.append(f"Dropped unconfigured {kind} '{candidate}'.")
            continue
        if matched not in kept:
            kept.append(matched)

    return kept


def _evidence_supported(evidence: Any, question: str) -> bool:
    """
    Whether quoted evidence actually appears in the question.

    A cheap fabrication check. The comparison is on normalized alphanumerics so
    that punctuation and casing do not produce false alarms, and a missing or
    empty quote is treated as unsupported rather than as absent-and-fine.
    """
    if not isinstance(evidence, str) or not evidence.strip():
        return False

    def norm(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    quote = norm(evidence)
    return bool(quote) and quote in norm(question)


def _normalize_words(text: str) -> List[str]:
    """Alphanumeric words of a string, lowercased. Shared by the checks below."""
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).split()


def _validate_value_phrases(
    raw_phrases: Any,
    question: str,
    metric_terms: List[str],
    dimension_names: List[str],
    notes: List[str],
) -> List[ValuePhrase]:
    """
    Keep only value spans the question actually contains.

    Four independent reasons to drop a phrase, each of which has a matching
    failure we have already seen in production:

      not in the question   - the model paraphrased or invented a value.
      names a metric        - "pending" is the Pending Amount metric, not a
                              value; letting it be both is how one word ends up
                              filtering on itself.
      already seen          - the same span twice is one filter, not two.
      over the cap          - MAX_VALUE_PHRASES; the rest are dropped loudly.

    `dimension` survives only when it is a configured dimension name, and
    `qualifier_explicit` is then computed HERE, from the question, by checking
    the user actually wrote a word of that dimension's name. The model's own
    opinion on that is not consulted - it proposes the binding, the question
    decides whether the user really made it.

    An unconfigured dimension does not discard the phrase: the user still named
    a value, they just named it against something we cannot verify, so the
    binding is dropped and the phrase continues unqualified.
    """
    if not isinstance(raw_phrases, list):
        return []

    question_words = set(_normalize_words(question))
    metric_words = {w for term in metric_terms for w in _normalize_words(term)}

    kept: List[ValuePhrase] = []
    seen: set = set()

    for raw in raw_phrases:
        if isinstance(raw, str):
            raw = {"phrase": raw}
        if not isinstance(raw, dict):
            continue

        phrase = raw.get("phrase")
        if not isinstance(phrase, str) or not phrase.strip():
            continue
        phrase = phrase.strip()

        if not _evidence_supported(phrase, question):
            notes.append(
                f"Dropped value phrase '{phrase}': not present in the question."
            )
            continue

        phrase_words = _normalize_words(phrase)
        if phrase_words and all(w in metric_words for w in phrase_words):
            notes.append(
                f"Dropped value phrase '{phrase}': it names a metric, not a value."
            )
            continue

        identity = " ".join(phrase_words)
        if identity in seen:
            continue

        if len(kept) >= MAX_VALUE_PHRASES:
            notes.append(
                f"Dropped value phrase '{phrase}': more than "
                f"{MAX_VALUE_PHRASES} value phrases were proposed."
            )
            continue

        dimension = None
        raw_dimension = raw.get("dimension")
        if isinstance(raw_dimension, str) and raw_dimension.strip():
            matched = _validate_terms(
                [raw_dimension], dimension_names, "value-phrase dimension", notes
            )
            dimension = matched[0] if matched else None

        # Deterministic, from the question - never from the model.
        qualifier_explicit = bool(dimension) and any(
            word in question_words
            for word in _normalize_words(dimension)
            if word not in phrase_words
        )
        if dimension and not qualifier_explicit:
            notes.append(
                f"Value phrase '{phrase}' was bound to '{dimension}', but the "
                f"question does not name that dimension; treated as unqualified."
            )

        seen.add(identity)
        kept.append(
            ValuePhrase(
                phrase=phrase,
                dimension=dimension,
                qualifier_explicit=qualifier_explicit,
                confidence=coerce_confidence(raw.get("confidence")),
            )
        )

    return kept


def _parse_payload(
    payload: dict,
    question: str,
    metric_names: List[str],
    dimension_names: List[str],
) -> ExtractedIntent:
    """Turn a parsed model object into a validated ExtractedIntent."""
    intent = ExtractedIntent()
    notes: List[str] = []

    raw_conf = payload.get("confidence")
    confidence = raw_conf if isinstance(raw_conf, dict) else {}
    raw_evidence = payload.get("evidence")
    evidence = raw_evidence if isinstance(raw_evidence, dict) else {}

    def take(slot: SlotName, value: Any) -> Optional[Any]:
        """
        Accept one enum-valued slot, with its confidence discounted when the
        model could not quote the question for it.
        """
        if value is None:
            return None
        score = coerce_confidence(confidence.get(slot.value))
        quote = evidence.get(slot.value)

        if quote is not None and not _evidence_supported(quote, question):
            notes.append(
                f"Evidence for {slot.value} ('{quote}') is not in the question; "
                f"confidence reduced."
            )
            score = min(score, LOW_CONFIDENCE - 0.01)

        intent.confidence[slot.value] = score
        if isinstance(quote, str):
            intent.evidence[slot.value] = quote
        return value

    intent.mode = take(SlotName.MODE, coerce_enum(SlotName.MODE, payload.get("mode")))
    intent.direction = take(SlotName.DIRECTION, coerce_enum(SlotName.DIRECTION, payload.get("direction")))
    intent.measure = take(SlotName.MEASURE, coerce_enum(SlotName.MEASURE, payload.get("measure")))
    intent.benchmark = take(SlotName.BENCHMARK, coerce_enum(SlotName.BENCHMARK, payload.get("benchmark")))
    intent.output = take(SlotName.OUTPUT, coerce_enum(SlotName.OUTPUT, payload.get("output")))
    intent.top_n = take(SlotName.TOP_N, coerce_top_n(payload.get("top_n")))

    time_period = payload.get("time_period")
    if isinstance(time_period, str) and time_period.strip():
        intent.time_period = take(SlotName.TIME_PERIOD, time_period.strip())

    comparison = payload.get("comparison_period")
    if isinstance(comparison, str) and comparison.strip():
        intent.comparison_period = take(SlotName.COMPARISON, comparison.strip())

    intent.metric_terms = _validate_terms(
        payload.get("metric_terms"), metric_names, "metric", notes
    )
    intent.dimension_terms = _validate_terms(
        payload.get("dimension_terms"), dimension_names, "dimension", notes
    )

    if intent.metric_terms:
        intent.confidence[SlotName.METRIC.value] = coerce_confidence(
            confidence.get(SlotName.METRIC.value, confidence.get("metric_terms"))
        )
    if intent.dimension_terms:
        intent.confidence[SlotName.DIMENSION.value] = coerce_confidence(
            confidence.get(SlotName.DIMENSION.value, confidence.get("dimension_terms"))
        )

    # After metric_terms, which the overlap check below reads.
    intent.value_phrases = _validate_value_phrases(
        payload.get("value_phrases"),
        question,
        intent.metric_terms,
        dimension_names,
        notes,
    )
    if intent.value_phrases:
        intent.confidence[SlotName.VALUE_PHRASE.value] = min(
            p.confidence for p in intent.value_phrases
        )

    unknown = payload.get("unknown_terms")
    if isinstance(unknown, list):
        for term in unknown:
            if isinstance(term, str) and term.strip():
                notes.append(f"User term '{term.strip()}' is not in the semantic layer.")

    intent.notes = notes
    return intent


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

# Slots where the two readings are compared and a disagreement escalates.
# All four are enum- or integer-valued, so "differs" is exact.
_RECONCILED_SLOTS = (
    SlotName.MODE,
    SlotName.DIRECTION,
    SlotName.MEASURE,
    SlotName.TOP_N,
)

# Slots the deterministic pass only fills when the model left them empty.
# These hold free text, where the two passes routinely produce different
# wording for the same period ("last quarter" / "the last quarter"). Comparing
# them for equality would manufacture disagreements and escalate questions that
# nobody is actually confused about.
_FILL_ONLY_SLOTS = (
    SlotName.TIME_PERIOD,
    SlotName.COMPARISON,
)


def _reconcile(
    model_intent: ExtractedIntent,
    deterministic: ExtractedIntent,
) -> Tuple[ExtractedIntent, List[SlotName]]:
    """
    Merge the model reading with the deterministic reading.

    Three cases per slot:

      only one side filled it   -> take that side
      both agree                -> keep it, raise confidence, it is corroborated
      both filled, disagreeing  -> keep the model's value but mark the slot
                                   low-confidence so step 26 escalates it

    Disagreement deliberately does not pick a winner. The deterministic pass is
    exact but narrow and the model is broad but approximate; when they conflict,
    the honest state is "unresolved", and unresolved is what escalation is for.
    """
    disputed: List[SlotName] = []

    for slot in _RECONCILED_SLOTS:
        model_value = model_intent.value_for(slot)
        det_value = deterministic.value_for(slot)

        if det_value is None:
            continue

        if model_value is None:
            _assign(model_intent, slot, det_value)
            model_intent.confidence[slot.value] = deterministic.confidence_for(slot)
            model_intent.notes.append(
                f"{slot.value} taken from wording; the model did not fill it."
            )
            continue

        if model_value == det_value:
            corroborated = max(
                model_intent.confidence_for(slot),
                deterministic.confidence_for(slot),
            )
            # Agreement between two independent readings is worth more than
            # either alone, but is capped below certainty: both can share a
            # blind spot on an unusual phrasing.
            model_intent.confidence[slot.value] = min(0.99, corroborated + 0.05)
            continue

        disputed.append(slot)
        model_intent.confidence[slot.value] = min(
            model_intent.confidence_for(slot), LOW_CONFIDENCE - 0.01
        )
        model_intent.notes.append(
            f"{slot.value}: wording suggests {det_value}, model said {model_value}."
        )

    for slot in _FILL_ONLY_SLOTS:
        det_value = deterministic.value_for(slot)
        if det_value is None:
            continue

        if model_intent.value_for(slot) is None:
            _assign(model_intent, slot, det_value)
            model_intent.confidence[slot.value] = deterministic.confidence_for(slot)
            model_intent.evidence[slot.value] = str(det_value)
            continue

        # Both found a period. The wording is independent corroboration that one
        # was stated, even where the two passes phrase it differently, so the
        # model's score is floored at the deterministic one. Without this a
        # model that fills the field but omits its confidence entry scores 0.0
        # and escalates a question nobody is confused about.
        model_intent.confidence[slot.value] = max(
            model_intent.confidence_for(slot),
            deterministic.confidence_for(slot),
        )

    for note in deterministic.unsupported:
        if note not in model_intent.unsupported:
            model_intent.unsupported.append(note)

    return model_intent, disputed


def _assign(intent: ExtractedIntent, slot: SlotName, value: Any) -> None:
    if slot == SlotName.MODE:
        intent.mode = value
    elif slot == SlotName.DIRECTION:
        intent.direction = value
    elif slot == SlotName.MEASURE:
        intent.measure = value
    elif slot == SlotName.TOP_N:
        intent.top_n = value
    elif slot == SlotName.BENCHMARK:
        intent.benchmark = value
    elif slot == SlotName.OUTPUT:
        intent.output = value
    elif slot == SlotName.TIME_PERIOD:
        intent.time_period = value
    elif slot == SlotName.COMPARISON:
        intent.comparison_period = value
    elif slot == SlotName.VALUE_PHRASE:
        intent.value_phrases = list(value or [])


def _apply_mode_consistency(intent: ExtractedIntent) -> None:
    """
    Structural rules that hold regardless of wording.

    Ranking fields on a non-ranking plan are meaningless, and a ranking with a
    change measure but no direction is under-specified. These are corrected or
    flagged here rather than left for the plan builder, so the plan the guards
    see is internally consistent.
    """
    if intent.mode is not None and intent.mode != AnalysisMode.RANKING:
        for slot, value in (
            (SlotName.DIRECTION, intent.direction),
            (SlotName.MEASURE, intent.measure),
            (SlotName.TOP_N, intent.top_n),
        ):
            if value is not None:
                intent.notes.append(
                    f"Cleared {slot.value}: it only applies to a RANKING plan."
                )
                _assign(intent, slot, None)
                intent.confidence.pop(slot.value, None)

    # A ranking that names a count but no direction is the ordinary "top 5"
    # case: the head word carries the direction. Only fill it when the wording
    # actually contained a head word, never as a blanket default.
    if intent.mode == AnalysisMode.RANKING and intent.measure is None and intent.top_n is not None:
        intent.measure = RankMeasure.ABSOLUTE
        intent.confidence[SlotName.MEASURE.value] = 0.75
        intent.notes.append(
            "Measure defaulted to ABSOLUTE: the question ranks without "
            "describing movement."
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_intent(
    question: str,
    connection_id: Optional[str] = None,
    company_id: Optional[str] = None,
    history_summary: str = "",
    vocabulary: Any = None,
    invoke=None,
) -> ExtractedIntent:
    """
    Read one question into a validated ExtractedIntent.

    `invoke` replaces the model call in tests: it takes (purpose, prompt) and
    returns raw text. Injected rather than patched so a test can exercise the
    reconciliation and escalation logic without a provider, a database or a
    network.
    """
    question = (question or "").strip()
    deterministic = read_deterministic_signals(question)

    if not question:
        return deterministic

    metric_names: List[str] = []
    dimension_names: List[str] = []

    if vocabulary is None and connection_id:
        try:
            from semantic import vocabulary_service
            vocabulary = vocabulary_service.get_vocabulary(connection_id)
        except Exception as exc:
            logger.warning(
                "Vocabulary unavailable for extraction (%s); "
                "configured-term validation will drop every term.",
                str(exc).splitlines()[0][:160],
            )

    if vocabulary is not None:
        metric_names = list(vocabulary.metric_names())
        dimension_names = list(vocabulary.dimension_names())

    caller = invoke or (lambda purpose, prompt: _call_with_fallback(purpose, prompt, company_id))

    prompt = build_extraction_prompt(
        question=question,
        metric_names=metric_names,
        dimension_names=dimension_names,
        history_summary=history_summary,
    )

    raw = caller(PRIMARY_PURPOSE, prompt)
    payload = _extract_json(raw) if raw else None

    if payload is None:
        # No usable model output. The deterministic reading is still a correct
        # reading of the wording, so it is returned rather than discarded.
        deterministic.escalation_tier = EscalationTier.UNAVAILABLE
        deterministic.notes.append(
            "No model extraction was available; wording-derived slots only."
        )
        _apply_mode_consistency(deterministic)
        return deterministic

    intent = _parse_payload(payload, question, metric_names, dimension_names)
    intent, disputed = _reconcile(intent, deterministic)
    intent.escalation_tier = EscalationTier.PRIMARY

    weak = sorted(
        {slot for slot in intent.low_confidence_slots()} | set(disputed),
        key=lambda s: s.value,
    )

    if weak:
        intent = _escalate(
            intent=intent,
            weak=weak,
            question=question,
            metric_names=metric_names,
            dimension_names=dimension_names,
            caller=caller,
        )

    _apply_mode_consistency(intent)
    return intent


def _escalate(
    intent: ExtractedIntent,
    weak: List[SlotName],
    question: str,
    metric_names: List[str],
    dimension_names: List[str],
    caller,
) -> ExtractedIntent:
    """
    Step 26 - ask the stronger model about the fields the first pass fumbled.

    The stronger model's answer is accepted only where it is confident. Where it
    is not, the slot is left as it was and a clarification is raised, because
    two uncertain readings do not add up to one certain one.
    """
    prompt = build_escalation_prompt(
        question=question,
        weak_slots=[slot.value for slot in weak],
        first_pass=intent.to_dict(),
        metric_names=metric_names,
        dimension_names=dimension_names,
    )

    raw = caller(ESCALATION_PURPOSE, prompt)
    payload = _extract_json(raw) if raw else None

    intent.escalation_tier = EscalationTier.ESCALATED

    if payload is None:
        intent.notes.append("Escalation produced no usable answer.")
        return _clarify_if_needed(intent, weak)

    raw_conf = payload.get("confidence")
    confidence = raw_conf if isinstance(raw_conf, dict) else {}

    for slot in weak:
        if slot.value not in payload:
            continue

        score = coerce_confidence(confidence.get(slot.value))
        if score < LOW_CONFIDENCE:
            intent.notes.append(
                f"Escalation was also unsure about {slot.value} ({score:.2f})."
            )
            continue

        if slot == SlotName.VALUE_PHRASE:
            # Re-validated from scratch against the same question. The stronger
            # model gets no more trust than the first one did - only a second
            # attempt at the same checks.
            value = _validate_value_phrases(
                payload.get(slot.value),
                question,
                intent.metric_terms,
                dimension_names,
                intent.notes,
            ) or None
        elif slot == SlotName.TOP_N:
            value = coerce_top_n(payload.get(slot.value))
        elif slot in (SlotName.TIME_PERIOD, SlotName.COMPARISON):
            candidate = payload.get(slot.value)
            value = candidate.strip() if isinstance(candidate, str) and candidate.strip() else None
        else:
            value = coerce_enum(slot, payload.get(slot.value))

        if value is None:
            continue

        _assign(intent, slot, value)
        intent.confidence[slot.value] = score
        intent.notes.append(f"{slot.value} resolved by escalation to {value}.")

    return _clarify_if_needed(intent, weak)


def _clarify_if_needed(intent: ExtractedIntent, weak: List[SlotName]) -> ExtractedIntent:
    """
    Raise one narrow clarification when escalation left a slot unresolved.

    Only the first unresolved slot produces a question. Asking about three
    fields at once is how a clarification becomes an interrogation, and the
    first one is usually the one whose answer settles the rest.
    """
    for slot in weak:
        if intent.confidence_for(slot) >= LOW_CONFIDENCE:
            continue
        if intent.confidence_for(slot) < CLARIFY_CONFIDENCE or intent.value_for(slot) is None:
            intent.clarification = _clarification_for(slot, intent)
            if intent.clarification is not None:
                intent.escalation_tier = EscalationTier.CLARIFY
                return intent

    return intent


def _clarification_for(slot: SlotName, intent: ExtractedIntent) -> Optional[Clarification]:
    """
    The specific question to ask for one unresolved slot.

    Each names its alternatives. A clarification that cannot list the options is
    not raised at all - the pipeline proceeds with what it has rather than
    asking the user to guess what it wants.
    """
    if slot == SlotName.MEASURE:
        return Clarification(
            slot=slot.value,
            question=(
                "Do you want the ones with the lowest values, or the ones that "
                "changed the most?"
            ),
            options=["Lowest values", "Biggest change", "Biggest percentage change"],
            reason="The question could be read as ranking on the level or on the movement.",
        )

    if slot == SlotName.DIRECTION:
        return Clarification(
            slot=slot.value,
            question="Should that be the highest first, or the lowest first?",
            options=["Highest first", "Lowest first"],
            reason="The question contains cues for both directions.",
        )

    if slot == SlotName.MODE:
        return Clarification(
            slot=slot.value,
            question="What would you like me to do with that?",
            options=["Show the figures", "Compare periods", "Show the trend", "Rank them"],
            reason="The kind of analysis requested was not clear.",
        )

    return None
