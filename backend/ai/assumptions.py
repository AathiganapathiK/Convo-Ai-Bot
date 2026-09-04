"""
Gate 4 Steps 28 and 29 - assume, record, and say so.

THE RULE, IN ONE LINE

Ask the user only when there is nothing safe to assume.

Every slot the pipeline needs falls into exactly one of three states, and only
the third is allowed to interrupt:

    stated          the user said it            -> use it
    absent          the user did not say it     -> use the conventional default,
                                                   and write a sentence into
                                                   plan.assumptions_made
    contradictory   the user said two things,
                    or said something unusable  -> ask one narrow question that
                                                   names the alternatives

The middle case is the point of the gate. The system used to stop and ask
whenever a slot was empty, which is why a user answering three clarifications
before seeing a number learned not to bother asking. An absent slot with an
obvious convention is not ambiguity; it is a question the user did not think
needed saying, and answering it while showing the assumption is both faster and
more honest than interrogating them.

APPEND, NEVER REPLACE

assumptions_made is written by more than one stage. The plan builder already
records the snapshot-configuration fallback there before this module runs, and
Gate 3 writes to it too. Everything here appends. A stage that assigns the list
wholesale silently deletes another stage's disclosure, and the user then sees a
number resting on an assumption nobody told them about.

THE ONE DECISION THIS MODULE WILL NOT MAKE

What a missing time period should default to is a business ruling that has not
been made. It is called out as an open question in the Gate 3 / Gate 4 handoff
and it is not code's to settle, so MISSING_PERIOD_POLICY below ships as DEFER -
assume nothing, ask nothing, leave the plan with no temporal constraint, which
is exactly the behaviour that shipped before this gate. Both live alternatives
are implemented and tested; switching is a one-line change once the team rules.
See the module note at MISSING_PERIOD_POLICY for what each option does.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from ai.extraction.models import Clarification, ExtractedIntent, SlotName
from semantic.models.semantic_plan import AnalysisMode, OutputFormat, RankDirection

logger = logging.getLogger(__name__)


class MissingPeriodPolicy(str, Enum):
    """
    What to do when a question names no time period.

    DEFER  - do nothing. No period is assumed, none is asked for, and the plan
             carries no temporal constraint. This is the pre-Gate-4 behaviour
             and the shipping default while the ruling is outstanding.
    ASSUME - use the conventional period, record it in assumptions_made, and
             show it to the user with an invitation to change it. This is the
             option the handoff document's author favours: because periods in
             this database are snapshot columns rather than date filters,
             assuming is cheap and reversible.
    ASK    - raise a narrow clarification naming the available periods. Correct
             but costly; it interrupts every period-less question.
    """
    DEFER = "DEFER"
    ASSUME = "ASSUME"
    ASK = "ASK"


# ---------------------------------------------------------------------------
# THE OPEN BUSINESS DECISION
# ---------------------------------------------------------------------------
# Do not change this without a recorded ruling from the team. Changing it alters
# the answer to every question that omits a period, which is most of them.
#
#   DEFER  (current) - no period assumed. Safe, and identical to today.
#   ASSUME           - current year assumed and disclosed.
#   ASK              - user asked every time.
#
# The conventional period below is only consulted under ASSUME.
MISSING_PERIOD_POLICY = MissingPeriodPolicy.DEFER

CONVENTIONAL_PERIOD = "the current year"


@dataclass
class AssumptionOutcome:
    """
    What step 28 decided.

    `assumptions` are sentences to append to plan.assumptions_made - already
    phrased for a business reader, because they are shown verbatim.
    `clarification` is set only when nothing safe could be assumed.
    """
    assumptions: List[str] = field(default_factory=list)
    clarification: Optional[Clarification] = None
    applied: dict = field(default_factory=dict)

    @property
    def needs_user(self) -> bool:
        return self.clarification is not None


# ---------------------------------------------------------------------------
# Defaults that are safe to apply without asking
# ---------------------------------------------------------------------------
# "Safe" has a specific meaning here: applying the default and being wrong
# costs the user one glance and one follow-up, and never produces a number that
# looks like an answer to a different question. A default that could change
# which rows are counted is not safe and is not listed.

# A ranking with no stated count. Ten is the convention the existing prompt
# layer already uses for unbounded rankings, so this changes nothing about the
# result - it only makes the choice visible.
DEFAULT_TOP_N = 10


def _default_top_n(intent: ExtractedIntent, outcome: AssumptionOutcome) -> None:
    """
    Fill a ranking's row count.

    Only for RANKING plans. A count on a descriptive plan would silently
    truncate a breakdown the user asked to see in full, which is the kind of
    quiet wrongness this gate exists to remove.
    """
    if intent.mode != AnalysisMode.RANKING:
        return
    if intent.top_n is not None:
        return

    intent.top_n = DEFAULT_TOP_N
    outcome.applied[SlotName.TOP_N.value] = DEFAULT_TOP_N
    outcome.assumptions.append(
        f"Showing the top {DEFAULT_TOP_N} - ask for more or fewer if you need "
        f"a different number."
    )


def _default_direction(intent: ExtractedIntent, outcome: AssumptionOutcome) -> None:
    """
    Fill a ranking's direction.

    Descending is the convention for "top"/"rank" with no qualifier, and it is
    what the Gate 1 heuristic in the plan builder already does. Recorded rather
    than assumed silently, so a user who meant the other end can see why they
    got what they got.
    """
    if intent.mode != AnalysisMode.RANKING:
        return
    if intent.direction is not None:
        return

    intent.direction = RankDirection.DESC
    outcome.applied[SlotName.DIRECTION.value] = RankDirection.DESC.value
    outcome.assumptions.append(
        "Ordered highest first - say 'lowest' if you wanted the other end."
    )


def _default_output(intent: ExtractedIntent, outcome: AssumptionOutcome) -> None:
    """
    Presentation only. Never recorded as an assumption.

    How a number is displayed does not change what the number is, so disclosing
    it would add noise to every answer for no protection. The plan builder's
    existing shape-to-format mapping remains the source of truth; this only
    fills the gap when extraction produced a mode but no format.
    """
    if intent.output is not None or intent.mode is None:
        return

    intent.output = {
        AnalysisMode.RANKING: OutputFormat.TABLE,
        AnalysisMode.TREND: OutputFormat.CHART,
        AnalysisMode.COMPARISON: OutputFormat.TABLE,
        AnalysisMode.DESCRIPTIVE: OutputFormat.KPI,
    }.get(intent.mode)


def _handle_missing_period(intent: ExtractedIntent, outcome: AssumptionOutcome) -> None:
    """
    Apply whichever missing-period policy is in force.

    Under DEFER this is a no-op by design, not an oversight: see the module
    docstring. The branch exists so that switching the policy is genuinely one
    line and so that all three behaviours are covered by tests today.
    """
    if intent.time_period is not None:
        return

    if MISSING_PERIOD_POLICY == MissingPeriodPolicy.DEFER:
        intent.notes.append(
            "No time period stated. No period assumed: the business rule for "
            "this case has not been settled."
        )
        return

    if MISSING_PERIOD_POLICY == MissingPeriodPolicy.ASSUME:
        intent.time_period = CONVENTIONAL_PERIOD
        outcome.applied[SlotName.TIME_PERIOD.value] = CONVENTIONAL_PERIOD
        outcome.assumptions.append(
            f"Assuming {CONVENTIONAL_PERIOD} - say the word for a different period."
        )
        return

    outcome.clarification = Clarification(
        slot=SlotName.TIME_PERIOD.value,
        question="Which period should I use?",
        options=["This year", "Last year", "Year to date"],
        reason="The question did not name a period and no default is configured.",
    )


def _contradiction_check(intent: ExtractedIntent, outcome: AssumptionOutcome) -> None:
    """
    Catch the third state - the user said something that cannot be honoured.

    A clarification already raised by the extractor wins: it was raised closer
    to the evidence and names better options than anything reconstructible here.
    """
    if intent.clarification is not None:
        outcome.clarification = intent.clarification
        return

    # A ranking that orders on movement but names no comparison period cannot be
    # computed: there is no second period to difference against. This is a real
    # contradiction rather than an absence, so it asks rather than assuming.
    from semantic.models.semantic_plan import RankMeasure

    if (
        intent.mode == AnalysisMode.RANKING
        and intent.measure in (RankMeasure.CHANGE, RankMeasure.CHANGE_PCT)
        and not intent.time_period
        and not intent.comparison_period
    ):
        outcome.clarification = Clarification(
            slot=SlotName.COMPARISON.value,
            question="Change compared with which period?",
            options=["Versus last year", "Versus last quarter", "Versus last month"],
            reason=(
                "Ranking by change needs two periods to compare, and the "
                "question named none."
            ),
        )


def resolve(intent: ExtractedIntent) -> AssumptionOutcome:
    """
    Step 28. Fill what is safely fillable, ask about what is not.

    Mutates `intent` in place - the caller passes the extraction it is about to
    build a plan from, and expects the filled version back. The returned outcome
    carries the sentences to append and any clarification to raise.
    """
    outcome = AssumptionOutcome()

    _contradiction_check(intent, outcome)
    if outcome.needs_user:
        # Nothing is defaulted while a contradiction is outstanding. Filling
        # defaults now would produce a plan that looks complete next to a
        # question admitting it is not.
        return outcome

    _default_direction(intent, outcome)
    _default_top_n(intent, outcome)
    _default_output(intent, outcome)
    _handle_missing_period(intent, outcome)

    return outcome


def merge_into(existing: Any, additions: List[str]) -> List[str]:
    """
    Append disclosures to an existing assumptions_made list.

    Order preserved, duplicates dropped. Never returns the same list object the
    caller passed, because SemanticPlan is frozen and its list must be rebuilt
    rather than mutated in place.
    """
    merged: List[str] = []
    seen = set()

    for source in (existing or [], additions or []):
        for item in source:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)

    return merged


# ---------------------------------------------------------------------------
# Step 29 - showing assumptions to the user
# ---------------------------------------------------------------------------

def render_for_user(assumptions: List[str]) -> str:
    """
    The block appended to an answer.

    Phrased as statements with the correction built in, because an assumption
    the user cannot see how to change is just a hidden decision with extra
    words. Every default written above already carries its own "say X for Y",
    so this only frames them.
    """
    cleaned = [str(a).strip() for a in (assumptions or []) if str(a).strip()]
    if not cleaned:
        return ""

    if len(cleaned) == 1:
        return f"_{cleaned[0]}_"

    lines = "\n".join(f"- {item}" for item in cleaned)
    return f"I filled in a few things you did not specify:\n{lines}"


def render_clarification(clarification: Clarification) -> str:
    """
    The narrow question, with its options laid out for selection.

    Never a bare "please clarify": the options are the whole value of asking,
    and a question without them costs the user a turn and tells them nothing.
    """
    if clarification is None:
        return ""

    if not clarification.options:
        return clarification.question

    options = "\n".join(f"- {option}" for option in clarification.options)
    return f"{clarification.question}\n{options}"


def describe_unsupported(intent: ExtractedIntent) -> str:
    """
    Step 27's honest limit.

    A diagnostic or prescriptive question gets a descriptive answer today,
    because Gates 8 and 9 do not exist yet. Returning the figures without saying
    so lets the user believe the "why" was answered. This says it was not.
    """
    if not intent.unsupported:
        return ""

    said: List[str] = []

    if AnalysisMode.DIAGNOSTIC.value in intent.unsupported:
        said.append(
            "You asked why this happened. I can show what happened, but I "
            "cannot yet work out the cause."
        )
    if AnalysisMode.PRESCRIPTIVE.value in intent.unsupported:
        said.append(
            "You asked what to do about it. I can show the figures, but I "
            "cannot yet recommend actions."
        )

    return " ".join(said)
