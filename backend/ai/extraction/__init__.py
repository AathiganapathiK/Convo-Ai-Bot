"""
Gate 4 - structured intent extraction.

Public surface kept deliberately small: callers want an ExtractedIntent and the
one function that produces it. The prompts and the deterministic pattern set are
implementation detail and are imported directly by the tests that exercise them.
"""

from ai.extraction.models import (
    CLARIFY_CONFIDENCE,
    Clarification,
    EscalationTier,
    ExtractedIntent,
    LOW_CONFIDENCE,
    SlotName,
)
from ai.extraction.slot_extractor import extract_intent, read_deterministic_signals

__all__ = [
    "CLARIFY_CONFIDENCE",
    "Clarification",
    "EscalationTier",
    "ExtractedIntent",
    "LOW_CONFIDENCE",
    "SlotName",
    "extract_intent",
    "read_deterministic_signals",
]
