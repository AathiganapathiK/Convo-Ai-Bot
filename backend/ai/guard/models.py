"""
Gate 5 - structured result models for the SQL Guard.

The guard answers one question: does the generated SQL implement the semantic
plan it was generated from? These models carry that verdict.

Deliberately mirrors the conventions already established by ai/ast/schema.py -
a str Enum of codes, a dataclass per violation, and a result object holding
passed plus a list of violations - so the guard reads like the validators that
already exist beside it.
"""

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """
    How seriously a violation should be treated.

    Four levels rather than a simple pass/fail because the semantic plan is not
    yet trustworthy. Resolution currently passes a minority of its own
    benchmark and the analysis mode is still derived from keyword matching, so
    a disagreement between plan and SQL does not reliably mean the SQL is
    wrong - it may mean the plan is. Collapsing that into a single FAIL would
    block correct SQL generated from an incorrect plan.
    """

    # The SQL implements the plan as far as the guard can tell.
    PASS = "PASS"

    # The SQL differs from the plan in a way that may be legitimate, usually
    # because the plan itself is incomplete or ambiguous. Logged, never blocks.
    WARNING = "WARNING"

    # The SQL contradicts the plan unambiguously, and the contradiction is one
    # a regeneration could plausibly fix when handed the exact violation.
    # Bounded retry is appropriate. Introduced in Step 31/32.
    REPAIRABLE_FAILURE = "REPAIRABLE_FAILURE"

    # Objectively wrong regardless of whether the plan was right: the SQL will
    # not parse, or there is nothing to verify against. Never executes, and is
    # never blindly retried.
    HARD_FAILURE = "HARD_FAILURE"


# Ordered weakest to strongest. Used to reduce a set of violations to the one
# severity that describes the result.
_SEVERITY_ORDER = [
    Severity.PASS,
    Severity.WARNING,
    Severity.REPAIRABLE_FAILURE,
    Severity.HARD_FAILURE,
]


class ViolationCode(str, Enum):
    """
    Machine-readable classification of what went wrong.

    Every code here is raised by a rule that exists. Codes for grouping,
    ordering, limits and joins belong to Batch B and Batch C and are added
    alongside the rules that raise them, so the enum never contains values
    nothing can produce.
    """

    # --- Step 30: the SQL could not be checked at all --------------------

    # The SQL could not be parsed at all.
    SQL_PARSE_FAILURE = "SQL_PARSE_FAILURE"

    # No SQL was supplied, or it was blank.
    EMPTY_SQL = "EMPTY_SQL"

    # No plan was supplied. The guard cannot verify conformance against
    # nothing, so it refuses rather than passing by default.
    MISSING_PLAN = "MISSING_PLAN"

    # --- Step 31 Batch A: does the SQL measure the right thing? ----------

    # The plan's metric column is absent and a different column is being
    # aggregated instead. The classic silent error: a plausible number
    # computed from the wrong column.
    METRIC_MISMATCH = "METRIC_MISMATCH"

    # The plan's metric column does not appear in the query at all.
    MISSING_METRIC = "MISSING_METRIC"

    # The right column, the wrong arithmetic - AVG where the plan said SUM.
    AGGREGATION_MISMATCH = "AGGREGATION_MISMATCH"

    # --- Step 31 Batch A: is the SQL looking at the right rows? ----------

    # A filter the plan requires is not present in the SQL. The query answers
    # a broader question than the one that was asked.
    MISSING_FILTER = "MISSING_FILTER"

    # The right filter column, the wrong value - Karnataka where the plan
    # said Tamil Nadu. Returns a number that looks entirely reasonable.
    FILTER_VALUE_MISMATCH = "FILTER_VALUE_MISMATCH"

    # The right column and value, but an incompatible operator - an exclusion
    # where the plan expected an inclusion.
    FILTER_OPERATOR_MISMATCH = "FILTER_OPERATOR_MISMATCH"

    # The SQL filters on a column the plan never asked to filter on. Narrows
    # the result set in a way the plan did not intend.
    UNEXPECTED_FILTER = "UNEXPECTED_FILTER"

    # The SQL selects a column beyond what the plan asked for. Adds a column
    # to the output but does not change the rows or the figures, so this is
    # reported as a note rather than an error.
    UNEXPECTED_SELECTION = "UNEXPECTED_SELECTION"

    # --- Step 31 Batch B: is the answer the right shape? -----------------

    # A dimension the plan asked to break the figures down by is not in the
    # GROUP BY, so the totals are aggregated more coarsely than requested.
    MISSING_GROUPING = "MISSING_GROUPING"

    # The SQL groups by a column the plan did not ask for, splitting the
    # totals across more rows than intended.
    UNEXPECTED_GROUPING = "UNEXPECTED_GROUPING"

    # The plan asked for a fixed number of rows and the SQL returns a
    # different number - top 50 where top 5 was requested.
    LIMIT_MISMATCH = "LIMIT_MISMATCH"

    # The plan asked for a ranking of N rows and the SQL caps nothing, so the
    # whole result set comes back instead.
    MISSING_LIMIT = "MISSING_LIMIT"

    # The plan ranked ascending and the SQL ranks descending, or vice versa.
    # Inverts the answer: worst performers presented as best.
    ORDER_DIRECTION_MISMATCH = "ORDER_DIRECTION_MISMATCH"

    # The plan asked for a ranking but the SQL has no ORDER BY. TOP N without
    # ORDER BY returns an arbitrary N rows, so the answer is not merely
    # unsorted - it is non-deterministic.
    MISSING_ORDER_BY = "MISSING_ORDER_BY"

    # --- Step 31 Batch C: are the tables connected correctly? ------------

    # The plan requires two tables to be joined and the SQL does not join
    # them, or joins one of them to something else entirely.
    JOIN_MISMATCH = "JOIN_MISMATCH"

    # The right two tables are joined, but on different columns than the plan
    # specified. Produces a result set that looks plausible and pairs the
    # wrong rows together.
    JOIN_KEY_MISMATCH = "JOIN_KEY_MISMATCH"

    # Two or more tables appear with no condition linking them, so every row
    # of one is paired with every row of the other. Objectively wrong, and on
    # a large table it can exhaust the database.
    CARTESIAN_JOIN = "CARTESIAN_JOIN"

    # The SQL reads a table the plan never mentioned.
    UNEXPECTED_TABLE = "UNEXPECTED_TABLE"

    # --- Hidden restrictions and predicate integrity ---------------------

    # A required filter appears in the SQL but is not guaranteed - it sits in
    # an OR branch or under a NOT, so rows can come back without it applying.
    FILTER_NOT_GUARANTEED = "FILTER_NOT_GUARANTEED"

    # An OR branch that is true for every row, such as "OR 1=1". The WHERE
    # clause looks restrictive and restricts nothing.
    ALWAYS_TRUE_PREDICATE = "ALWAYS_TRUE_PREDICATE"

    # A HAVING clause the plan did not ask for, which drops groups from the
    # result after aggregation.
    UNEXPECTED_HAVING = "UNEXPECTED_HAVING"

    # SELECT DISTINCT where the plan did not request de-duplication.
    UNEXPECTED_DISTINCT = "UNEXPECTED_DISTINCT"

    # A row limit the plan never requested. Silently answers "the top few"
    # when the question asked for the whole result.
    UNEXPECTED_LIMIT = "UNEXPECTED_LIMIT"

    # --- Step 33: is the written answer supported by the results? --------

    # The answer quotes a figure that does not appear in the returned rows,
    # in any form the model was shown them.
    UNSUPPORTED_NUMBER = "UNSUPPORTED_NUMBER"

    # The query returned nothing, yet the answer states figures anyway.
    NUMBERS_WITHOUT_RESULTS = "NUMBERS_WITHOUT_RESULTS"

    # The answer states a number of records that does not match how many rows
    # the query actually returned.
    ROW_COUNT_MISMATCH = "ROW_COUNT_MISMATCH"

    # The answer names a year outside the period the query covered.
    PERIOD_CONTRADICTION = "PERIOD_CONTRADICTION"

    # The plan totals its metric, but the answer calls the figure an average.
    AGGREGATION_WORDING_CONTRADICTION = "AGGREGATION_WORDING_CONTRADICTION"

    # A percentage or other figure that appears to be calculated rather than
    # read from the results. Which values were combined is not recoverable, so
    # this is recorded rather than treated as an error.
    UNSUPPORTED_CALCULATION = "UNSUPPORTED_CALCULATION"

    # A capitalised value in the answer that is absent from the results. Often
    # a synonym rather than a mistake, so it never blocks.
    ENTITY_NOT_IN_RESULTS = "ENTITY_NOT_IN_RESULTS"


@dataclass
class Violation:
    """
    One specific way the SQL failed to match the plan.

    expected and actual are optional because a parse failure has no
    plan-versus-SQL comparison to report - they carry the two sides of a
    mismatch once the Step 31 rules exist.
    """

    code: ViolationCode
    severity: Severity
    message: str
    expected: str | None = None
    actual: str | None = None

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


@dataclass
class GuardResult:
    """
    The guard's verdict on one plan/SQL pair.

    Carries the extracted metadata alongside the verdict so a caller - and the
    Step 31 rules - can inspect what the SQL actually did without re-parsing it.
    """

    passed: bool
    severity: Severity
    violations: list[Violation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # The SQL as supplied, and as normalised by sqlglot.
    sql: str | None = None
    serialized_sql: str | None = None

    # SQLMetadata extracted by the existing AST extractor. None when parsing
    # failed, which is precisely when there is nothing to inspect.
    metadata: object | None = None

    @property
    def blocked(self) -> bool:
        """
        Whether this result should stop the query executing.

        Only HARD_FAILURE blocks today. REPAIRABLE_FAILURE becomes blocking
        when Step 32 wires the guard in behind a retry; WARNING never blocks.
        """
        return self.severity == Severity.HARD_FAILURE

    def codes(self) -> list[str]:
        """Violation codes, for concise assertions and structured logging."""
        return [v.code.value for v in self.violations]


def resolve_severity(violations: list[Violation]) -> Severity:
    """
    Reduce a set of violations to the single severity describing the result.

    The strongest severity wins: one hard failure makes the whole result a hard
    failure, however many warnings accompany it.
    """

    severity = Severity.PASS

    for violation in violations:
        if _SEVERITY_ORDER.index(violation.severity) > _SEVERITY_ORDER.index(severity):
            severity = violation.severity

    return severity
