"""
Gate 4 Step 25 - the contract the extractor returns.

WHY EVERY FIELD CARRIES A CONFIDENCE

The failure this gate exists to fix is not "the model got it wrong". It is "the
model got it wrong and nobody could tell". A single overall score cannot express
the common real case: the metric is obvious, the ranking measure is a coin flip.
Escalating the whole extraction because one field is shaky wastes a call to the
larger model; escalating nothing because the average looked fine is how a wrong
confident answer gets shipped. So confidence is per field, and step 26 decides
per field.

WHY THE ENUMS ARE IMPORTED, NEVER REDEFINED

AnalysisMode, RankDirection, RankMeasure, BenchmarkType and OutputFormat all
already exist in semantic/models/semantic_plan.py, where Gate 1 put them and
where the plan builder and both guards read them. Redeclaring any of them here
would create two vocabularies that drift, and the guard would start rejecting
plans over a spelling difference. This module imports them and adds nothing to
them.

WHAT "NO VALUE" MEANS

Every slot is Optional and defaults to None, and None means the user did not
say. It does not mean zero, or the default, or "unknown so pick something".
Step 28 is the only place allowed to turn a None into a value, and when it does
it writes a sentence into assumptions_made saying so.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from semantic.models.semantic_plan import (
    AnalysisMode,
    BenchmarkType,
    OutputFormat,
    RankDirection,
    RankMeasure,
)


class EscalationTier(str, Enum):
    """
    How much work went into producing an extraction, recorded on the result.

    Kept as an explicit record rather than inferred from confidence, because
    "the fast model was sure" and "the strong model was sure" are different
    facts about the same number and only the tier distinguishes them.
    """
    PRIMARY = "PRIMARY"          # fast model, confident, nothing further needed
    ESCALATED = "ESCALATED"      # a field was weak; the stronger model was asked
    CLARIFY = "CLARIFY"          # still unresolved; the user must be asked
    DETERMINISTIC = "DETERMINISTIC"   # answered without any model at all
    UNAVAILABLE = "UNAVAILABLE"  # no model could be reached; nothing extracted


class SlotName(str, Enum):
    """
    The slots step 26 and step 28 reason about individually.

    A closed set, because confidence dictionaries keyed by free strings are how
    a typo silently disables an escalation rule.
    """
    MODE = "mode"
    DIRECTION = "direction"
    MEASURE = "measure"
    TOP_N = "top_n"
    BENCHMARK = "benchmark"
    OUTPUT = "output"
    METRIC = "metric"
    DIMENSION = "dimension"
    TIME_PERIOD = "time_period"
    COMPARISON = "comparison"


# Below this, a field is not trusted on its own and step 26 escalates it.
# Chosen to sit above the band where this model class produces plausible-looking
# guesses. Deliberately not tunable per call: a threshold that every caller may
# override is a threshold nobody can reason about.
LOW_CONFIDENCE = 0.70

# Below this, even the stronger model's answer is not accepted, and the user is
# asked instead. A wrong confident answer is worse than a clarification.
CLARIFY_CONFIDENCE = 0.50


@dataclass
class Clarification:
    """
    One narrow question, with the specific alternatives that provoked it.

    `options` is required in spirit: a clarification that cannot name the
    choices is the generic "please rephrase" that step 28 exists to abolish.
    Callers that cannot populate options should not be raising a clarification.
    """
    slot: str
    question: str
    options: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "slot": self.slot,
            "question": self.question,
            "options": list(self.options),
            "reason": self.reason,
        }


@dataclass
class ExtractedIntent:
    """
    One structured reading of one question.

    Slots hold what the user actually said. `confidence` holds how sure the
    extractor is per slot, keyed by SlotName values. `evidence` holds the user's
    own wording for each slot, kept verbatim so that a later stage can quote the
    question back rather than paraphrasing it - "you said 'reducing'" is
    checkable, "you wanted a decrease" is not.
    """

    mode: Optional[AnalysisMode] = None
    direction: Optional[RankDirection] = None
    measure: Optional[RankMeasure] = None
    top_n: Optional[int] = None
    benchmark: Optional[BenchmarkType] = None
    output: Optional[OutputFormat] = None

    metric_terms: List[str] = field(default_factory=list)
    dimension_terms: List[str] = field(default_factory=list)

    time_period: Optional[str] = None
    comparison_period: Optional[str] = None

    confidence: Dict[str, float] = field(default_factory=dict)
    evidence: Dict[str, str] = field(default_factory=dict)

    escalation_tier: EscalationTier = EscalationTier.PRIMARY
    clarification: Optional[Clarification] = None

    # Capabilities the question asks for that this system cannot deliver yet.
    # Step 27 populates this so the answer can say so plainly instead of
    # producing a descriptive answer to a diagnostic question and letting the
    # user assume the "why" was addressed.
    unsupported: List[str] = field(default_factory=list)

    # Free-text notes from validation, surfaced in diagnostics rather than to
    # the user. Kept so a reviewer can see why a model value was overridden.
    notes: List[str] = field(default_factory=list)

    # Sentences describing defaults step 28 filled in on the user's behalf.
    # Carried here so the plan builder can append them to plan.assumptions_made
    # without importing ai.assumptions - the builder stays free of a Gate 4
    # dependency and simply copies whatever it is handed.
    assumptions_made: List[str] = field(default_factory=list)

    def confidence_for(self, slot: SlotName) -> float:
        """Confidence for one slot; 0.0 when the extractor said nothing."""
        return float(self.confidence.get(slot.value, 0.0))

    def is_low(self, slot: SlotName) -> bool:
        """
        Whether a slot needs escalation.

        A slot the user never mentioned is not low confidence - it is absent,
        and absence is step 28's problem, not step 26's. Only a slot that was
        filled but weakly justifies spending a stronger model call.
        """
        if self.value_for(slot) is None:
            return False
        return self.confidence_for(slot) < LOW_CONFIDENCE

    def value_for(self, slot: SlotName) -> Any:
        return {
            SlotName.MODE: self.mode,
            SlotName.DIRECTION: self.direction,
            SlotName.MEASURE: self.measure,
            SlotName.TOP_N: self.top_n,
            SlotName.BENCHMARK: self.benchmark,
            SlotName.OUTPUT: self.output,
            SlotName.METRIC: self.metric_terms or None,
            SlotName.DIMENSION: self.dimension_terms or None,
            SlotName.TIME_PERIOD: self.time_period,
            SlotName.COMPARISON: self.comparison_period,
        }.get(slot)

    def low_confidence_slots(self) -> List[SlotName]:
        return [slot for slot in SlotName if self.is_low(slot)]

    def to_dict(self) -> dict:
        """Diagnostic form. Enum members become their values for logging."""
        return {
            "mode": self.mode.value if self.mode else None,
            "direction": self.direction.value if self.direction else None,
            "measure": self.measure.value if self.measure else None,
            "top_n": self.top_n,
            "benchmark": self.benchmark.value if self.benchmark else None,
            "output": self.output.value if self.output else None,
            "metric_terms": list(self.metric_terms),
            "dimension_terms": list(self.dimension_terms),
            "time_period": self.time_period,
            "comparison_period": self.comparison_period,
            "confidence": dict(self.confidence),
            "evidence": dict(self.evidence),
            "escalation_tier": self.escalation_tier.value,
            "clarification": self.clarification.to_dict() if self.clarification else None,
            "unsupported": list(self.unsupported),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Enum coercion
# ---------------------------------------------------------------------------
# A model returns strings. These turn a string into an enum member or into
# None, and never into a new enum value. Anything unrecognised is dropped with
# a note rather than passed through, because an invented mode reaching the plan
# is exactly the failure this gate is supposed to prevent.

_ENUMS = {
    SlotName.MODE: AnalysisMode,
    SlotName.DIRECTION: RankDirection,
    SlotName.MEASURE: RankMeasure,
    SlotName.BENCHMARK: BenchmarkType,
    SlotName.OUTPUT: OutputFormat,
}


def coerce_enum(slot: SlotName, raw: Any) -> Optional[Any]:
    """
    Turn a model's string into the matching enum member, or None.

    Matching is case-insensitive on both the member name and its value, because
    OutputFormat's values are lowercase ("kpi") while every other enum here uses
    uppercase, and a model asked for "KPI" is not wrong about the concept.
    """
    if raw is None:
        return None

    enum_cls = _ENUMS.get(slot)
    if enum_cls is None:
        return None

    if isinstance(raw, enum_cls):
        return raw

    candidate = str(raw).strip()
    if not candidate:
        return None

    for member in enum_cls:
        if candidate.upper() == member.name.upper():
            return member
        if candidate.upper() == str(member.value).upper():
            return member

    return None


def coerce_top_n(raw: Any) -> Optional[int]:
    """
    A positive row count, or None.

    Zero and negatives are rejected rather than clamped: "top 0 products" is not
    a request for one product, it is a misread, and silently turning it into a
    number would hide that.
    """
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def coerce_confidence(raw: Any) -> float:
    """
    A score in [0, 1]. Anything unparseable is 0.0 - unknown confidence is no
    confidence, which routes the field to escalation rather than to acceptance.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if value != value:  # NaN
        return 0.0
    return max(0.0, min(1.0, value))
