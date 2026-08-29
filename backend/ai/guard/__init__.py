"""
Gate 5 - the SQL Guard.

Verifies that SQL generated from a semantic plan actually implements that
plan, before the SQL is allowed to execute.

Step 30 provides the skeleton only: parse, extract, and return a structured
verdict. The conformance rules arrive in Step 31 and the wiring into the live
validation pipeline in Step 32.
"""

from .models import (
    GuardResult,
    Severity,
    Violation,
    ViolationCode,
    resolve_severity,
)
from .plan_conformance import verify_sql_against_plan
from .predicates import (
    ExtractedPredicate,
    extract_predicates,
    normalize_identifier,
    normalize_value,
)

__all__ = [
    "GuardResult",
    "Severity",
    "Violation",
    "ViolationCode",
    "resolve_severity",
    "verify_sql_against_plan",
    "ExtractedPredicate",
    "extract_predicates",
    "normalize_identifier",
    "normalize_value",
]
