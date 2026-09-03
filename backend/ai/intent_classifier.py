"""
ai/intent_classifier.py

Gate 4 Steps 22 and 23 - the three-way router.

WHAT CHANGED AND WHY

This file used to hold two hardcoded keyword lists describing the AdventureWorks
demo database: reseller, salesperson, subcategory, orderdate, unitprice. This
customer sells dhotis, banians and shirtings. Every routing decision was made
against vocabulary belonging to a different business, and "sales" sat in the
strong list, so a single occurrence forced the analytical pipeline with no
further thought.

Those lists are gone. Routing evidence now comes from the semantic layer for the
active connection, through semantic.vocabulary_service, which applies Gate 2's
exclusions via semantic.runtime_config_filter. A column an administrator hid
does not come back as a routing keyword.

THREE DESTINATIONS, NOT TWO

    SMALL_TALK  greetings, thanks, chit-chat. Answered conversationally.
                No resolver, no plan, no SQL.
    METADATA    "what can I ask?", "what fields do you have?", "do you track
                returns?". Answered from the semantic registry itself. No SQL.
    ANALYTICAL  the only destination that enters the resolver.

METADATA is the new one and it earns its place. Before, "what can I ask?" was
answered either by a general chat model - which invents plausible field names
this business does not have - or by generating SQL against a question that has
no SQL answer. Both produce confident fiction about the product's own
capabilities, which is the worst place to be wrong.

ORDER OF EVIDENCE

    1. small talk, deterministic, whole-phrase
    2. metadata, deterministic, requires a capability cue
    3. analytical, from configured vocabulary
    4. the model, only when the first three are silent

Deterministic stages run first because they are exact and free. The model is
consulted for the genuinely ambiguous remainder, which is what it is good at.

BACKWARD COMPATIBILITY

classify_intent() still returns the two legacy strings "ANALYTICS" and
"GENERAL", because app.py branches on them and thirty-odd tests patch it. The
three-way decision is exposed through route_question(), which is what a caller
wanting the METADATA destination should use. Until app.py is updated, METADATA
maps to GENERAL, which is exactly where those questions went before - so this
file changes no behaviour it is not supposed to change.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class Destination(str, Enum):
    """Where a question goes. The whole point of step 22."""
    SMALL_TALK = "SMALL_TALK"
    METADATA = "METADATA"
    ANALYTICAL = "ANALYTICAL"


# Legacy values app.py and the existing test suite still speak.
LEGACY_ANALYTICS = "ANALYTICS"
LEGACY_GENERAL = "GENERAL"


@dataclass
class RoutingDecision:
    """
    A destination plus why it was chosen.

    The reason is not decoration: routing is the one decision that determines
    whether anything else in the pipeline runs, and a misroute with no recorded
    cause is close to undebuggable in production logs.
    """
    destination: Destination
    reason: str = ""
    method: str = ""                      # "keyword" | "vocabulary" | "llm"
    matched_terms: List[str] = field(default_factory=list)

    @property
    def legacy(self) -> str:
        """The two-valued answer, for callers not yet updated."""
        return (
            LEGACY_ANALYTICS
            if self.destination == Destination.ANALYTICAL
            else LEGACY_GENERAL
        )

    def to_dict(self) -> dict:
        return {
            "destination": self.destination.value,
            "reason": self.reason,
            "method": self.method,
            "matched_terms": list(self.matched_terms),
        }


# ---------------------------------------------------------------------------
# Stage 1 - small talk
# ---------------------------------------------------------------------------
# Anchored to the whole utterance, not searched within it. "Hello, what were
# sales last month" is a data question with a greeting attached, and matching
# "hello" anywhere would send it to chit-chat and never answer it. These
# patterns therefore describe complete short utterances only.

_SMALL_TALK_PATTERNS = [
    r"(hi|hello|hey|yo|hiya|howdy)",
    r"good\s+(morning|afternoon|evening|day)",
    r"(thanks|thank\s+you|thankyou|ty|cheers|nice|great|cool|awesome|perfect|ok|okay)",
    r"(bye|goodbye|see\s+you|good\s?night)",
    r"how\s+are\s+you(\s+doing)?",
    r"who\s+are\s+you",
    r"what\s+is\s+your\s+name",
    r"(help|help\s+me)",
    r"(sorry|my\s+bad|never\s?mind|nvm)",
    r"(yes|no|yep|nope|sure|maybe)",
    r"what\s+can\s+you\s+do",
]

_SMALL_TALK = re.compile(
    r"^\s*(?:" + "|".join(_SMALL_TALK_PATTERNS) + r")[\s!.,?]*$",
    re.IGNORECASE,
)

# "What can you do" is small talk about the assistant, but in a data product the
# honest answer is the capability list. Routed to METADATA instead, because
# answering it from the semantic registry is strictly more useful than a
# generated pleasantry.
_CAPABILITY_SMALL_TALK = re.compile(
    r"^\s*(?:what\s+can\s+you\s+do|help|help\s+me)[\s!.,?]*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Stage 2 - metadata
# ---------------------------------------------------------------------------
# A metadata question asks about the shape of the data rather than its contents.
# Both halves must be present: a capability frame ("what can I", "do you have")
# AND a schema noun ("fields", "metrics", "data"). Requiring both is what keeps
# "what were sales" - a capability frame with no schema noun - out of here.

_CAPABILITY_FRAME = re.compile(
    r"\b("
    r"what\s+can\s+i\s+(ask|query|see|do)|"
    r"what\s+(kind|sort|type)s?\s+of|"
    r"what\s+(data|fields?|columns?|metrics?|measures?|dimensions?|"
    r"tables?|reports?|domains?|areas?)\b|"
    r"which\s+(data|fields?|columns?|metrics?|measures?|dimensions?)\b|"
    r"do\s+you\s+(have|track|store|know|support|hold)|"
    r"can\s+you\s+(tell\s+me\s+)?(what|which)|"
    r"is\s+there\s+(a|any)\s+|"
    r"list\s+(the\s+)?(fields?|columns?|metrics?|measures?|dimensions?|tables?)|"
    r"show\s+me\s+(the\s+)?(fields?|columns?|metrics?|measures?|dimensions?|schema)|"
    r"tell\s+me\s+about\s+(the\s+)?(data|schema|fields?|metrics?)"
    r")\b",
    re.IGNORECASE,
)

_SCHEMA_NOUN = re.compile(
    r"\b(data|dataset|database|schema|field|fields|column|columns|"
    r"metric|metrics|measure|measures|dimension|dimensions|"
    r"table|tables|report|reports|domain|domains|area|areas|"
    r"question|questions|ask|capabilities|track|available)\b",
    re.IGNORECASE,
)


def _is_metadata(question: str) -> bool:
    """
    Whether this asks about the data rather than for the data.

    Both a capability frame and a schema noun are required. "Do you track
    returns?" has both. "Do you have the sales figure for March?" has the frame
    but its noun is a value, not a schema noun, so it correctly falls through to
    the analytical stage.
    """
    if not _CAPABILITY_FRAME.search(question):
        return False
    return bool(_SCHEMA_NOUN.search(question))


# ---------------------------------------------------------------------------
# Stage 3 - analytical, from the semantic layer
# ---------------------------------------------------------------------------
# These are the only literal words left in this file, and they are deliberately
# business-neutral: they describe analytical operations in English, not this or
# any other customer's schema. The subject matter always comes from the
# configured vocabulary.

_ANALYTICAL_OPERATIONS = re.compile(
    r"\b(total|sum|average|avg|count|how\s+many|how\s+much|"
    r"top|bottom|highest|lowest|best|worst|rank|ranking|"
    r"trend|trends|growth|compare|comparison|versus|vs|"
    r"breakdown|break\s+down|split|distribution|share|"
    r"by\s+month|by\s+year|by\s+quarter|month\s+wise|year\s+wise|"
    r"last\s+(year|month|quarter|week)|this\s+(year|month|quarter|week)|"
    r"year\s+to\s+date|ytd|mtd|"
    r"performance|percentage|percent)\b",
    re.IGNORECASE,
)


def _vocabulary_stage(question: str, connection_id: Optional[str]) -> Optional[RoutingDecision]:
    """
    Route on this business's own configured terms.

    Two independent routes to ANALYTICAL:

      a configured term plus an analytical operation - "total sales" - which is
      unambiguous, or

      two or more distinct configured terms - "sales by brand" - because naming
      two things from the semantic layer in one sentence is not something small
      talk does.

    A single configured term with no operation deliberately does NOT route here.
    "Brand" on its own could be a data question or a topic change, and the model
    stage is better placed to tell than a counting rule is.
    """
    if not connection_id:
        return None

    try:
        from semantic import vocabulary_service
        vocabulary = vocabulary_service.get_vocabulary(connection_id)
    except Exception as exc:
        logger.warning(
            "Routing vocabulary unavailable (%s); deferring to the model stage.",
            str(exc).splitlines()[0][:160],
        )
        return None

    if vocabulary.is_empty:
        return None

    matches = vocabulary.find_matches(question)
    if not matches:
        return None

    terms = [m.canonical for m in matches]
    has_operation = bool(_ANALYTICAL_OPERATIONS.search(question))

    if has_operation:
        return RoutingDecision(
            destination=Destination.ANALYTICAL,
            reason=(
                f"Configured term(s) {terms} with an analytical operation."
            ),
            method="vocabulary",
            matched_terms=terms,
        )

    # Without an operation, generic names such as Amount or Name are not enough
    # on their own - two distinct specific terms are required.
    specific = vocabulary.specific_matches(question)
    if len({m.canonical for m in specific}) >= 2:
        return RoutingDecision(
            destination=Destination.ANALYTICAL,
            reason=f"Multiple configured terms named together: {terms}.",
            method="vocabulary",
            matched_terms=terms,
        )

    return None


# ---------------------------------------------------------------------------
# Stage 4 - the model
# ---------------------------------------------------------------------------

_LLM_PROMPT = """\
Classify this message from a user of a business analytics assistant.

Answer with exactly one word:

SMALL_TALK - a greeting, thanks, or conversation not about the business data.
METADATA   - asking what the assistant knows or can answer, rather than asking
             for a figure. "What can I ask?", "do you track returns?"
ANALYTICAL - asking for a number, a list, a comparison or a breakdown from the
             business data.

When the message asks for a figure from the data, answer ANALYTICAL.
When it asks about the data itself, answer METADATA.

Message:
{question}
"""


def _llm_stage(question: str, company_id: Optional[str] = None) -> RoutingDecision:
    """
    The model decides what the deterministic stages could not.

    Any failure routes to SMALL_TALK. That is the safe direction: a data
    question misrouted to conversation costs the user a rephrase, whereas a
    greeting misrouted into the analytical pipeline runs a resolver, a model
    call and possibly a query against a question that has no answer.
    """
    from services.llm_execution_service import LLMExecutionService

    raw = ""
    try:
        response = LLMExecutionService.execute(
            purpose="intent",
            messages=[{"role": "user", "content": _LLM_PROMPT.format(question=question)}],
            company_id=company_id,
        )
        if response and getattr(response, "choices", None):
            message = getattr(response.choices[0], "message", None)
            content = getattr(message, "content", None) if message else None
            raw = (content or "").strip().upper()
    except Exception as exc:
        logger.warning(
            "Intent model unavailable (%s); routing to small talk.",
            str(exc).splitlines()[0][:160],
        )
        return RoutingDecision(
            destination=Destination.SMALL_TALK,
            reason="Intent model unavailable; defaulted to conversation.",
            method="llm",
        )

    if "ANALYTICAL" in raw or "ANALYTICS" in raw:
        destination = Destination.ANALYTICAL
    elif "METADATA" in raw:
        destination = Destination.METADATA
    else:
        destination = Destination.SMALL_TALK

    logger.info("Intent | question=%r | method=LLM | raw=%r | -> %s", question, raw, destination)

    return RoutingDecision(
        destination=destination,
        reason=f"Model classified as {raw or 'nothing usable'}.",
        method="llm",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def route_question(
    question: str,
    connection_id: Optional[str] = None,
    company_id: Optional[str] = None,
) -> RoutingDecision:
    """
    Step 22. Decide where a question goes.

    Deterministic stages first, model last. Callers that can supply
    connection_id should: without it the vocabulary stage cannot run and more
    questions fall through to the model, which is slower and less accurate.
    """
    text = (question or "").strip()

    if not text:
        return RoutingDecision(
            destination=Destination.SMALL_TALK,
            reason="Empty message.",
            method="keyword",
        )

    if _CAPABILITY_SMALL_TALK.match(text):
        return RoutingDecision(
            destination=Destination.METADATA,
            reason="Asked what the assistant can do; answered from the registry.",
            method="keyword",
        )

    if _SMALL_TALK.match(text):
        return RoutingDecision(
            destination=Destination.SMALL_TALK,
            reason="Whole message is a conversational phrase.",
            method="keyword",
        )

    if _is_metadata(text):
        return RoutingDecision(
            destination=Destination.METADATA,
            reason="Asks about the data rather than for it.",
            method="keyword",
        )

    decision = _vocabulary_stage(text, connection_id)
    if decision is not None:
        return decision

    return _llm_stage(text, company_id)


def classify_intent(
    question: str,
    company_id: Optional[str] = None,
    connection_id: Optional[str] = None,
) -> str:
    """
    Legacy two-valued API: "ANALYTICS" or "GENERAL".

    Retained unchanged in signature and return values because app.py branches on
    them and a large number of existing tests patch this function. METADATA maps
    to GENERAL, which is where those questions already went, so no caller sees a
    behaviour change until it opts in by calling route_question().
    """
    return route_question(question, connection_id=connection_id, company_id=company_id).legacy


def answer_metadata(question: str, connection_id: Optional[str]) -> Optional[str]:
    """
    Step 24. The answer to a METADATA question, from configuration alone.

    Returns None when there is nothing configured to describe. A None must not
    be papered over with a generated reply: "I do not have configuration for
    this connection yet" is true, and an invented field list is not.
    """
    if not connection_id:
        return None

    from semantic import vocabulary_service

    coverage_term = _coverage_target(question)
    if coverage_term:
        tracked = vocabulary_service.check_coverage(connection_id, coverage_term)
        if tracked is True:
            return (
                f"Yes - '{coverage_term}' is configured, so you can ask about it."
            )
        if tracked is False:
            described = vocabulary_service.describe_capabilities(connection_id)
            tail = f"\n\n{described}" if described else ""
            return (
                f"No - I have nothing configured for '{coverage_term}', so I "
                f"cannot report on it.{tail}"
            )
        return None

    return vocabulary_service.describe_capabilities(connection_id, question)


_COVERAGE_QUESTION = re.compile(
    r"\b(?:do\s+you\s+(?:have|track|store|hold|know\s+about)|"
    r"is\s+there\s+(?:a|any)|can\s+i\s+(?:see|ask\s+about))\s+"
    r"(?:any\s+|the\s+|data\s+(?:on|for|about)\s+)?"
    r"([a-z][a-z\s]{1,40}?)\s*\??$",
    re.IGNORECASE,
)


def _coverage_target(question: str) -> Optional[str]:
    """
    The thing a "do you track X?" question is asking about.

    Returns None for open metadata questions, which have no single target and
    are answered with the full capability description instead.
    """
    match = _COVERAGE_QUESTION.search((question or "").strip())
    if not match:
        return None

    target = match.group(1).strip()

    # Trailing schema nouns are part of the frame, not the thing asked about:
    # "do you have brand data" is asking about Brand.
    target = re.sub(
        r"\s+(data|information|info|details|figures|numbers|fields?|columns?)$",
        "",
        target,
        flags=re.IGNORECASE,
    ).strip()

    return target or None
