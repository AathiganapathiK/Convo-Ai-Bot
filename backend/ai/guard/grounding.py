"""
Gate 6 Step 33 - answer grounding.

WHAT THIS CHECKS
    That factual claims in the generated summary are supported by the rows the
    database actually returned, and do not contradict the plan's period or
    aggregation.

WHAT IT DOES NOT AND CANNOT CHECK
    - Whether the semantic plan understood the question. That is Gates 3/4.
    - Whether the chosen period was the right period. Only whether the answer
      contradicts the period that was queried.
    - Causal or qualitative statements ("driven by festive demand"). No ground
      truth for these exists in the rows, so they are ignored entirely.
    - Arbitrary derived arithmetic. Which values the model combined is not
      recoverable, so a percentage that is not present in the rows is recorded
      as a note, never treated as proof of error.
    - Synonyms. Rows holding "TN" and an answer saying "Tamil Nadu" cannot be
      reconciled without a mapping this module deliberately does not own.

    A PASS therefore means "the figures quoted appear in the results", not
    "the answer is correct".

NO MODEL, NO DATABASE
    Every decision is exact comparison of parsed values. There is no LLM call,
    no embedding, no similarity score, no tolerance band. The rows passed in
    are the rows already returned by the query - nothing here queries anything.

WHY THE SUPPORTED SET IS BUILT FROM FORMATTED VALUES TOO
    The model is shown values through utils/value_formatter.format_value(),
    which applies Indian currency grouping and rounds to two decimals. A row
    holding 1234.567 is presented as a value ending .57, so the answer quoting
    .57 is accurate to what it was given. Both the raw value and the formatted
    value are therefore treated as supported.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

from ai.guard.models import Severity, Violation, ViolationCode, resolve_severity
from ai.guard.numbers import (
    extract_numeric_claims,
    extract_years,
    parse_number,
)
from utils.value_formatter import format_value


logger = logging.getLogger(__name__)


MODE_OFF = "off"
MODE_SHADOW = "shadow"
MODE_ENFORCE = "enforce"

_VALID_MODES = (MODE_OFF, MODE_SHADOW, MODE_ENFORCE)

MAX_REGENERATION_ATTEMPTS = 1


def get_grounding_mode() -> str:
    """
    Configured mode for answer grounding, defaulting to shadow.

    A separate variable from SQL_GUARD_MODE on purpose. The two guards fail in
    different ways and have different false-positive profiles: deciding that
    SQL conformance is safe to enforce says nothing about whether answer
    grounding is, and one switch controlling both would force that coupling.
    """

    mode = (os.getenv("ANSWER_GUARD_MODE", MODE_SHADOW) or "").strip().lower()

    if mode not in _VALID_MODES:
        logger.warning(
            "Unrecognised ANSWER_GUARD_MODE, falling back to shadow",
            extra={
                "event": "answer_guard_mode_invalid",
                "configured": mode,
                "valid": list(_VALID_MODES),
            },
        )
        return MODE_SHADOW

    return mode


@dataclass
class GroundingResult:
    """The verdict on one answer."""

    passed: bool
    severity: Severity
    violations: list = field(default_factory=list)
    supported_values: set = field(default_factory=set)
    row_count: int = 0

    def codes(self) -> list:
        return [v.code.value for v in self.violations]


@dataclass
class GroundingDecision:
    """What the caller should do with the answer."""

    answer: str
    blocked: bool = False
    message: Optional[str] = None
    mode: str = MODE_SHADOW
    retried: bool = False
    attempts: int = 0
    first_result: Optional[GroundingResult] = None
    final_result: Optional[GroundingResult] = None
    shadow_violation: bool = False

    def codes(self) -> list:
        result = self.final_result or self.first_result

        return result.codes() if result else []


# ---------------------------------------------------------------------------
# Building what the answer is allowed to say
# ---------------------------------------------------------------------------

def build_cell_values(rows: list) -> set:
    """
    Only the numeric values held in the returned cells.

    Kept separate from build_supported_values because arithmetic must be
    derived from data alone. Including the row count let "1,000,001" pass as
    "1,000,000 plus one row", which is not a derivation anybody would make and
    let a digit-altered figure through.
    """

    values = set()

    for row in rows or []:
        if not isinstance(row, dict):
            continue

        for column, value in row.items():
            if isinstance(value, bool) or value is None:
                continue

            if isinstance(value, (int, float, Decimal)):
                raw = parse_number(value)

                if raw is not None:
                    values.add(raw)

                formatted = parse_number(format_value(str(column), value))

                if formatted is not None:
                    values.add(formatted)

    return values


def build_supported_values(plan, rows: list) -> set:
    """
    Every number the answer may legitimately quote.

    Includes each numeric cell as stored and as the model was shown it, the
    number of rows, and numbers the plan itself states - a requested top N is a
    figure the answer may mention without it appearing in any cell.
    """

    supported = set()

    for row in rows or []:
        if not isinstance(row, dict):
            continue

        for column, value in row.items():
            if isinstance(value, bool) or value is None:
                continue

            if isinstance(value, (int, float, Decimal)):
                raw = parse_number(value)

                if raw is not None:
                    supported.add(raw)

                # What the model actually saw.
                formatted = parse_number(format_value(str(column), value))

                if formatted is not None:
                    supported.add(formatted)

    supported.add(Decimal(len(rows or [])))

    ranking = getattr(plan, "ranking", None)

    if ranking is not None and getattr(ranking, "top_n", None):
        supported.add(Decimal(ranking.top_n))

    return supported


# Pairwise derivation is quadratic, so it is capped. Summaries quote a handful
# of figures; beyond this the derived set would grow large enough that an
# invented number could coincide with a combination by chance, which is
# exactly the failure this validator exists to prevent.
MAX_VALUES_FOR_DERIVATION = 40


def build_derived_values(supported: set) -> set:
    """
    Values reconstructible from the returned figures by one arithmetic step.

    A summary comparing two states legitimately states their difference, and a
    difference is not present in any cell. Rejecting it was a false positive.

    Deliberately limited to a SINGLE operation between two returned values:
    difference and total. Chaining operations, or combining more than two
    values, would make almost any number reachable and hollow out the check.
    An invented figure that is not one subtraction or addition away from the
    data is still caught.
    """

    values = [v for v in supported if v is not None]

    if len(values) > MAX_VALUES_FOR_DERIVATION:
        return set()

    derived = set()

    for i, a in enumerate(values):
        for b in values[i + 1:]:
            derived.add(a - b)
            derived.add(b - a)
            derived.add(a + b)

    return derived


def build_derived_percentages(supported: set) -> set:
    """
    Percentage changes computable from two returned figures.

    growth = (current - previous) / previous * 100, rounded the ways a summary
    would normally write it. Only pairs actually present in the results are
    used, so a percentage the model invented is still reported.
    """

    values = [v for v in supported if v is not None and v != 0]

    if len(values) > MAX_VALUES_FOR_DERIVATION:
        return set()

    percentages = set()

    for a in values:
        for b in values:
            if a == b or b == 0:
                continue

            try:
                change = (a - b) / b * Decimal(100)
            except (InvalidOperation, ZeroDivisionError):
                continue

            for places in (Decimal("1"), Decimal("0.1"), Decimal("0.01")):
                try:
                    percentages.add(change.quantize(places))
                except InvalidOperation:
                    continue

            # A share of a total, as well as a change against it.
            try:
                share = a / b * Decimal(100)
            except (InvalidOperation, ZeroDivisionError):
                continue

            for places in (Decimal("1"), Decimal("0.1"), Decimal("0.01")):
                try:
                    percentages.add(share.quantize(places))
                except InvalidOperation:
                    continue

    return percentages


def build_supported_years(plan) -> set:
    """
    Years the answer may refer to, taken from the plan's temporal context.

    Empty when the plan records no dates, which switches period checking off
    rather than guessing - fiscal boundaries come from configuration, and this
    module must not reimplement them.
    """

    temporal = getattr(plan, "temporal", None)

    if temporal is None:
        return set()

    years = set()

    for attribute in ("start_date", "end_date"):
        value = getattr(temporal, attribute, None)

        if value is not None and hasattr(value, "year"):
            years.add(value.year)

    if not years:
        return set()

    # A fiscal year spans two calendar years, so the year on either side of the
    # queried range is legitimate to name.
    return {y for year in list(years) for y in (year - 1, year, year + 1)}


def build_supported_strings(rows: list, plan) -> set:
    """Every string value present in the results, plus the plan's filter values."""

    values = set()

    for row in rows or []:
        if not isinstance(row, dict):
            continue

        for value in row.values():
            if isinstance(value, str) and value.strip():
                values.add(value.strip().lower())

    for plan_filter in getattr(plan, "filters", None) or []:
        for value in getattr(plan_filter, "values", None) or []:
            if isinstance(value, str) and value.strip():
                values.add(value.strip().lower())

    return values


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

_ROW_COUNT_PATTERN = re.compile(
    r"\b(?P<count>\d[\d,]*)\s+"
    r"(?:records?|rows?|results?|entries|entrie?s)\b",
    re.IGNORECASE,
)

# Only fully capitalised tokens are treated as candidate data values. Title
# Case is far too common in ordinary prose ("Sales", "The") to distinguish from
# an entity name without a model, so it is excluded rather than guessed at.
_ALLCAPS_PATTERN = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")

_ALLCAPS_IGNORED = {
    "CY", "PY", "PYTD", "YTD", "MTD", "FY", "SQL", "KPI", "INR", "USD",
    "GST", "TOTAL", "NULL", "NOTE", "AND", "THE", "FOR", "ALL", "TOP",
    "SUM", "AVG", "MIN", "MAX", "QTY", "ID",
}

_AVERAGE_WORDS = re.compile(r"\b(?:average|averaged|averages|mean)\b", re.IGNORECASE)


def _check_numbers(
    claims,
    supported,
    rows,
    violations,
    derived=None,
    derived_percentages=None,
) -> None:
    """Every figure quoted must appear in, or be derivable from, the results."""

    has_rows = bool(rows)
    derived = derived or set()
    derived_percentages = derived_percentages or set()

    for claim in claims:
        # Years name a period, not a figure.
        if claim.is_bare_year:
            continue

        # A percentage that is not in the results is a derived calculation.
        # Which values the model combined is unknowable, so this is recorded
        # rather than treated as proof of error.
        if claim.is_percentage:
            if (
                claim.value not in supported
                and claim.value not in derived_percentages
            ):
                violations.append(
                    Violation(
                        code=ViolationCode.UNSUPPORTED_CALCULATION,
                        severity=Severity.WARNING,
                        message=(
                            f"The answer states '{claim.raw}', which is not a "
                            "value in the results. It appears to be derived, "
                            "and derived figures cannot be verified."
                        ),
                        expected="a percentage present in the results",
                        actual=claim.raw,
                    )
                )
            continue

        if claim.value in supported or claim.value in derived:
            continue

        if not has_rows:
            violations.append(
                Violation(
                    code=ViolationCode.NUMBERS_WITHOUT_RESULTS,
                    severity=Severity.REPAIRABLE_FAILURE,
                    message=(
                        f"The query returned no rows, but the answer states "
                        f"'{claim.raw}'. There is no data behind that figure."
                    ),
                    expected="no figures, because no rows were returned",
                    actual=claim.raw,
                )
            )
            continue

        violations.append(
            Violation(
                code=ViolationCode.UNSUPPORTED_NUMBER,
                severity=Severity.REPAIRABLE_FAILURE,
                message=(
                    f"The answer states '{claim.raw}', which does not appear "
                    "in the query results."
                ),
                expected="a value present in the query results",
                actual=claim.raw,
            )
        )


def _check_row_count(answer, rows, violations) -> None:
    actual = len(rows or [])

    for match in _ROW_COUNT_PATTERN.finditer(answer or ""):
        stated = parse_number(match.group("count"))

        if stated is None or stated == Decimal(actual):
            continue

        violations.append(
            Violation(
                code=ViolationCode.ROW_COUNT_MISMATCH,
                severity=Severity.REPAIRABLE_FAILURE,
                message=(
                    f"The answer says '{match.group(0).strip()}' but the query "
                    f"returned {actual}."
                ),
                expected=f"{actual} rows",
                actual=match.group(0).strip(),
            )
        )


def _check_period(answer, supported_years, violations) -> None:
    """
    The answer must not name a year outside the period that was queried.

    Skipped entirely when the plan records no dates - an absent temporal
    context is not evidence of a contradiction.
    """

    if not supported_years:
        return

    for year in sorted(extract_years(answer or "")):
        if year in supported_years:
            continue

        violations.append(
            Violation(
                code=ViolationCode.PERIOD_CONTRADICTION,
                severity=Severity.REPAIRABLE_FAILURE,
                message=(
                    f"The answer refers to {year}, but the query covered "
                    f"{min(supported_years)}-{max(supported_years)}."
                ),
                expected=f"a year within {min(supported_years)}-{max(supported_years)}",
                actual=str(year),
            )
        )


def _check_aggregation_wording(plan, answer, violations) -> None:
    """
    Averaging language when every metric in the plan is a sum.

    Narrow on purpose: it fires only when the plan has metrics, all of them
    aggregate with SUM, and none is an average. Anything looser would flag
    ordinary commentary.
    """

    metrics = getattr(plan, "metrics", None) or []

    if not metrics:
        return

    aggregations = {
        (m.aggregation_type or "").strip().upper()
        for m in metrics
        if m.aggregation_type
    }

    if not aggregations or aggregations != {"SUM"}:
        return

    if not _AVERAGE_WORDS.search(answer or ""):
        return

    violations.append(
        Violation(
            code=ViolationCode.AGGREGATION_WORDING_CONTRADICTION,
            severity=Severity.REPAIRABLE_FAILURE,
            message=(
                "The plan totals the metric with SUM, but the answer describes "
                "the figure as an average."
            ),
            expected="wording consistent with SUM",
            actual="the answer refers to an average",
        )
    )


def _check_entities(answer, supported_strings, violations) -> None:
    """
    Fully capitalised tokens that do not appear in the results.

    The weakest rule here, and a warning permanently unless measurement shows
    otherwise. Rows may hold a code where the answer uses a business name, and
    reconciling those needs a mapping this module deliberately does not own.
    """

    if not supported_strings:
        return

    for match in _ALLCAPS_PATTERN.finditer(answer or ""):
        token = match.group(0)

        if token.upper() in _ALLCAPS_IGNORED:
            continue

        candidate = token.strip().lower()

        # A value may appear as one word of a longer entry: the rows hold
        # "ABC Traders" while the answer writes "ABC". Matching whole strings
        # only reported a correct answer as unknown, so word-level containment
        # is checked as well. This is exact word matching, not fuzzy matching -
        # no edit distance, no similarity, no synonyms.
        if candidate in supported_strings:
            continue

        if any(candidate in value.split() for value in supported_strings):
            continue

        violations.append(
            Violation(
                code=ViolationCode.ENTITY_NOT_IN_RESULTS,
                severity=Severity.WARNING,
                message=(
                    f"The answer mentions '{token}', which does not appear in "
                    "the query results. It may be a synonym rather than an "
                    "error, so this is recorded and not treated as a fault."
                ),
                expected="a value present in the query results",
                actual=token,
            )
        )


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def verify_answer_against_results(plan, rows: list, answer: str) -> GroundingResult:
    """
    Check one generated answer against the rows it was written from.

    Pure: no model, no database, no global state. `rows` are the rows the query
    already returned; nothing here re-queries anything.
    """

    violations = []

    if not answer or not str(answer).strip():
        # Nothing was written, so there is nothing to ground. Whether an empty
        # answer is acceptable is not this validator's concern.
        return GroundingResult(
            passed=True,
            severity=Severity.PASS,
            row_count=len(rows or []),
        )

    answer = str(answer)

    supported = build_supported_values(plan, rows)
    supported_years = build_supported_years(plan)
    supported_strings = build_supported_strings(rows, plan)

    claims = extract_numeric_claims(answer)

    # Derived from the data cells only, never from the row count or the plan's
    # top-N. Those are not operands anybody would combine with a figure.
    cell_values = build_cell_values(rows)

    derived = build_derived_values(cell_values)
    derived_percentages = build_derived_percentages(cell_values)

    _check_numbers(
        claims,
        supported,
        rows,
        violations,
        derived=derived,
        derived_percentages=derived_percentages,
    )
    _check_row_count(answer, rows, violations)
    _check_period(answer, supported_years, violations)
    _check_aggregation_wording(plan, answer, violations)
    _check_entities(answer, supported_strings, violations)

    severity = resolve_severity(violations)

    return GroundingResult(
        passed=severity in (Severity.PASS, Severity.WARNING),
        severity=severity,
        violations=violations,
        supported_values=supported,
        row_count=len(rows or []),
    )


def format_grounding_feedback(result: GroundingResult) -> str:
    """Instructions for rewriting an answer that quoted unsupported figures."""

    lines = [
        "ANSWER GROUNDING FAILURE",
        "",
        "Your previous summary contained statements that are not supported by "
        "the query results:",
        "",
    ]

    for violation in result.violations:
        if violation.severity == Severity.WARNING:
            continue

        lines.append(f"- {violation.code.value}")
        lines.append(f"    Problem : {violation.message}")
        lines.append(f"    Expected: {violation.expected}")
        lines.append("")

    lines.append(
        "Rewrite the summary using only figures that appear in the query "
        "result shown above. Do not calculate new values, do not estimate, and "
        "do not mention periods other than the one queried. If a figure is not "
        "in the result, do not state it."
    )

    return "\n".join(lines)


def _log_result(result: GroundingResult, mode: str, attempt: int) -> None:
    if not result.violations:
        return

    logger.warning(
        "Answer grounding violation",
        extra={
            "event": "answer_grounding_violation",
            "mode": mode,
            "attempt": attempt,
            "passed": result.passed,
            "severity": result.severity.value,
            "codes": result.codes(),
            "row_count": result.row_count,
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
        },
    )


def ground_answer(
    *,
    plan,
    rows: list,
    answer: str,
    regenerate: Optional[Callable[[str], Optional[str]]] = None,
    mode: Optional[str] = None,
) -> GroundingDecision:
    """
    Validate an answer and, in enforce mode, rewrite it once if unsupported.

    The original plan and the original rows are used for both attempts. No SQL
    is regenerated here and no plan is rebuilt - that belongs to Step 32.
    """

    mode = (mode or get_grounding_mode()).strip().lower()

    if mode == MODE_OFF:
        return GroundingDecision(answer=answer, blocked=False, mode=mode)

    first = verify_answer_against_results(plan, rows, answer)

    _log_result(first, mode, attempt=1)

    decision = GroundingDecision(
        answer=answer,
        mode=mode,
        attempts=1,
        first_result=first,
        final_result=first,
    )

    if first.severity in (Severity.PASS, Severity.WARNING):
        return decision

    if mode == MODE_SHADOW:
        decision.shadow_violation = True
        return decision

    # --- enforce: exactly one rewrite -----------------------------------

    if regenerate is None:
        decision.blocked = True
        decision.message = _blocked_message(first)
        return decision

    feedback = format_grounding_feedback(first)

    try:
        rewritten = regenerate(feedback)
    except Exception as ex:
        logger.warning(
            "Answer regeneration failed",
            extra={
                "event": "answer_grounding_regeneration_error",
                "error": str(ex),
            },
        )
        decision.blocked = True
        decision.message = _blocked_message(first)
        return decision

    decision.retried = True
    decision.attempts = 2

    if not rewritten or not str(rewritten).strip():
        decision.blocked = True
        decision.message = _blocked_message(first)
        return decision

    rewritten = str(rewritten)

    # Checked against the same plan and the same rows.
    final = verify_answer_against_results(plan, rows, rewritten)

    _log_result(final, mode, attempt=2)

    decision.final_result = final

    if final.severity in (Severity.PASS, Severity.WARNING):
        decision.answer = rewritten
        return decision

    decision.blocked = True
    decision.message = _blocked_message(final)

    return decision


def _blocked_message(result: GroundingResult) -> str:
    reasons = "; ".join(
        f"{v.code.value} ({v.actual})"
        for v in result.violations
        if v.severity != Severity.WARNING
    )

    return (
        "The generated answer contained figures that are not supported by the "
        f"query results, and could not be corrected. Reason: {reasons}"
    )
