"""
Gate 5 Step 32 - wiring the plan-conformance guard into the request path.

WHAT THIS DOES
    Runs the deterministic Step 30/31 guard against generated SQL, and - once
    enforcement is switched on - regenerates the SQL exactly once when it
    disagrees with the plan.

WHAT IT DOES NOT DO
    No SQL is judged by a model here. The guard in plan_conformance.py remains
    the sole authority on whether SQL conforms, and it is pure comparison. A
    model is used for one thing only: writing a replacement query when the
    deterministic guard has already decided the first one was wrong.

MODES
    Read once from SQL_GUARD_MODE, defaulting to "shadow". There is no
    feature-flag framework in this project; configuration is environment based
    (core/config.py), and core/logger.py already reads a boolean toggle the
    same way, so this follows the established pattern rather than inventing an
    architecture.

        off      guard does not run at all
        shadow   guard runs, violations are logged, nothing is ever blocked
        enforce  violations block, with one regeneration attempt first

    Shadow is the default deliberately. The guard's real false-positive rate is
    unknown until it has been measured against production traffic, and blocking
    on an unmeasured rule would reject correct answers. Switching to enforce is
    a human decision, never automatic.

SEVERITY HANDLING (enforce mode)
    HARD_FAILURE        block immediately, no retry. A Cartesian join or an
                        unparseable query is wrong regardless of the plan, and
                        giving the model another attempt at it wastes a call.
    REPAIRABLE_FAILURE  regenerate exactly once, then re-check.
    WARNING             never blocks, never retries. These are the rules where
                        the plan is more likely wrong than the SQL.

ORDERING
    Called after the existing security and schema validation, and before row
    limiting and RLS injection. The guard therefore judges the SQL the model
    wrote, not the SQL after deterministic security predicates have been added
    to it - otherwise every RLS predicate would read as an unexpected filter.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

from ai.guard.models import GuardResult, Severity
from ai.guard.plan_conformance import verify_sql_against_plan


logger = logging.getLogger(__name__)


MODE_OFF = "off"
MODE_SHADOW = "shadow"
MODE_ENFORCE = "enforce"

_VALID_MODES = (MODE_OFF, MODE_SHADOW, MODE_ENFORCE)

# Exactly one regeneration. Not configurable: an unbounded or larger retry
# budget turns a wrong query into repeated model calls, and the second attempt
# already carries the precise reason the first failed.
MAX_REGENERATION_ATTEMPTS = 1


def get_guard_mode() -> str:
    """
    The configured guard mode, defaulting to shadow.

    An unrecognised value falls back to shadow rather than raising: a typo in
    an environment file must not take the application down, and shadow is the
    safe interpretation because it changes no outcome.
    """

    mode = (os.getenv("SQL_GUARD_MODE", MODE_SHADOW) or "").strip().lower()

    if mode not in _VALID_MODES:
        logger.warning(
            "Unrecognised SQL_GUARD_MODE, falling back to shadow",
            extra={
                "event": "plan_guard_mode_invalid",
                "configured": mode,
                "valid": list(_VALID_MODES),
            },
        )
        return MODE_SHADOW

    return mode


@dataclass
class GuardDecision:
    """
    What the caller should do with the query.

    `sql` is the query to carry forward - the original when nothing was
    regenerated, the replacement when it was. Callers must use this rather than
    their own copy, or a successful regeneration would be silently discarded.
    """

    sql: str
    blocked: bool = False
    message: Optional[str] = None
    mode: str = MODE_SHADOW
    retried: bool = False
    attempts: int = 0
    first_result: Optional[GuardResult] = None
    final_result: Optional[GuardResult] = None
    shadow_violation: bool = False

    def codes(self) -> list:
        result = self.final_result or self.first_result

        return result.codes() if result else []


def _is_conforming(result: GuardResult) -> bool:
    """
    Whether a guard result should be allowed through.

    WARNING passes deliberately - those rules exist to be recorded, not to
    block.
    """

    return result.severity in (Severity.PASS, Severity.WARNING)


def format_guard_feedback(result: GuardResult) -> str:
    """
    Turn violations into instructions for regeneration.

    Deliberately concrete. "The SQL does not match the plan" gives the model
    nothing to act on; naming the expected and actual value for each violation
    tells it exactly what to change.
    """

    lines = [
        "PLAN CONFORMANCE FAILURE",
        "",
        "The SQL you generated does not implement the supplied semantic plan.",
        "The following differences were detected deterministically:",
        "",
    ]

    for violation in result.violations:
        if violation.severity == Severity.WARNING:
            continue

        lines.append(f"- {violation.code.value}")
        lines.append(f"    Expected : {violation.expected}")
        lines.append(f"    Generated: {violation.actual}")
        lines.append(f"    Detail   : {violation.message}")
        lines.append("")

    lines.append(
        "Regenerate the SQL so that it conforms exactly to the supplied "
        "semantic plan. Change only what is listed above. Do not add filters, "
        "columns, groupings or joins that the plan does not specify."
    )

    return "\n".join(lines)


def _log_result(result: GuardResult, sql: str, mode: str, attempt: int) -> None:
    """
    Structured record of one guard evaluation.

    Follows the logging convention already used for the schema-validator
    shadow comparison in ai/sql_validator.py: a warning with an `event` key and
    structured detail in `extra`.
    """

    if _is_conforming(result) and not result.violations:
        return

    logger.warning(
        "Plan conformance violation",
        extra={
            "event": "plan_guard_violation",
            "mode": mode,
            "attempt": attempt,
            "passed": result.passed,
            "severity": result.severity.value,
            "codes": result.codes(),
            "violations": [
                {
                    "code": v.code.value,
                    "severity": v.severity.value,
                    "expected": v.expected,
                    "actual": v.actual,
                    "message": v.message,
                }
                for v in result.violations
            ],
            "sql": sql,
        },
    )


def guard_sql(
    *,
    plan,
    sql: str,
    regenerate: Optional[Callable[[str], Optional[str]]] = None,
    revalidate: Optional[Callable[[str], tuple]] = None,
    mode: Optional[str] = None,
) -> GuardDecision:
    """
    Check SQL against its plan and decide whether it may proceed.

    Args:
        plan: The SemanticPlan the SQL was generated from. A missing plan is
            a hard failure in enforce mode - the guard refuses rather than
            approving by default.
        sql: The model-generated SQL, before row limiting and RLS injection.
        regenerate: Called with structured feedback, returns replacement SQL.
            Injected so that tests exercise the retry with no model call.
        revalidate: Called with regenerated SQL, returns (ok, message). This is
            the complete existing validation pipeline - parse, security, schema
            and repair. Regenerated SQL is never assumed safe.
        mode: Overrides the configured mode. Used by tests.

    Returns:
        GuardDecision. In shadow mode `blocked` is always False and `sql` is
        always the query that was passed in, so the request outcome cannot
        differ from what it would have been without the guard.
    """

    mode = (mode or get_guard_mode()).strip().lower()

    if mode == MODE_OFF:
        return GuardDecision(sql=sql, blocked=False, mode=mode)

    first = verify_sql_against_plan(plan, sql)

    _log_result(first, sql, mode, attempt=1)

    decision = GuardDecision(
        sql=sql,
        mode=mode,
        attempts=1,
        first_result=first,
        final_result=first,
    )

    if _is_conforming(first):
        return decision

    # Shadow mode records and steps aside. It must not change the outcome of
    # the request in any way, which is the whole point of a measurement phase.
    if mode == MODE_SHADOW:
        decision.shadow_violation = True
        return decision

    # --- enforce ---------------------------------------------------------

    if first.severity == Severity.HARD_FAILURE:
        decision.blocked = True
        decision.message = _blocked_message(first, retried=False)
        return decision

    # REPAIRABLE_FAILURE: exactly one regeneration.
    if regenerate is None or revalidate is None:
        # Without both, the retry cannot be performed or the replacement
        # cannot be validated. Fail closed rather than executing SQL the guard
        # has already rejected.
        decision.blocked = True
        decision.message = _blocked_message(first, retried=False)
        return decision

    feedback = format_guard_feedback(first)

    try:
        regenerated = regenerate(feedback)
    except Exception as ex:
        logger.warning(
            "Plan guard regeneration failed",
            extra={
                "event": "plan_guard_regeneration_error",
                "error": str(ex),
            },
        )
        decision.blocked = True
        decision.message = _blocked_message(first, retried=False)
        return decision

    decision.retried = True
    decision.attempts = 2

    if not regenerated or not str(regenerated).strip():
        decision.blocked = True
        decision.message = _blocked_message(first, retried=True)
        return decision

    regenerated = str(regenerated)

    # The replacement is not trusted. It goes through the same parse, security
    # and schema validation as the original, from scratch.
    ok, message = revalidate(regenerated)

    if not ok:
        decision.blocked = True
        decision.message = (
            "The regenerated SQL failed validation and was not executed. "
            f"{message}"
        )
        return decision

    # Checked against the ORIGINAL plan. Regeneration rebuilds a plan of its
    # own, and judging the new SQL against a new plan could let a query pass
    # because the plan moved rather than because the SQL was corrected.
    final = verify_sql_against_plan(plan, regenerated)

    _log_result(final, regenerated, mode, attempt=2)

    decision.final_result = final

    if _is_conforming(final):
        decision.sql = regenerated
        return decision

    decision.blocked = True
    decision.message = _blocked_message(final, retried=True)

    return decision


def _blocked_message(result: GuardResult, retried: bool) -> str:
    reasons = "; ".join(
        f"{v.code.value} (expected {v.expected}, found {v.actual})"
        for v in result.violations
        if v.severity != Severity.WARNING
    )

    prefix = (
        "The generated SQL did not match the analytical plan, and the "
        "regenerated query did not either."
        if retried
        else "The generated SQL did not match the analytical plan."
    )

    return f"{prefix} It was not executed. Reason: {reasons}"
