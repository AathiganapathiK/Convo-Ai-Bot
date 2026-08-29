"""
Gate 5 Step 30 - the SQL Guard skeleton.

WHAT THIS IS FOR
    The system generates SQL from a semantic plan using an LLM. Nothing today
    proves the SQL it produced actually answers the question the plan
    describes. Schema validation already catches SQL that references columns
    which do not exist; it cannot catch SQL that is perfectly valid and answers
    a different question - AVG where the plan said SUM, Karnataka where the
    plan said Tamil Nadu. That gap is what this guard closes.

WHAT IS IMPLEMENTED (Step 31, Batch A)
    Four families of rule, all comparing structured plan fields against
    structured SQL metadata:

        metric column      the SQL aggregates the column the plan named
        aggregation        it applies the arithmetic the plan named
        filters            every filter the plan requires is present, on the
                           right column, with the right values and a
                           compatible operator
        extra operations   filters the plan never asked for are reported,
                           because they change which rows are counted

    Batch B (grouping, ordering, TOP/LIMIT) and Batch C (joins) are not
    implemented yet, and no code exists for them.

NO MODEL IS USED ANYWHERE IN THIS MODULE
    Every decision is an exact comparison of normalised values. There is no
    LLM call, no embedding, no similarity score and no threshold. Given the
    same plan and the same SQL, this returns the same verdict every time.

    Normalisation is limited to case, surrounding whitespace, table
    qualification, and numeric equality. Two genuinely different values never
    compare equal - the guard must never decide that Karnataka is close enough
    to Tamil Nadu.

WHAT A PASS MEANS - AND DOES NOT
    A PASS means "the generated SQL follows the semantic plan". It does NOT
    mean "the semantic plan correctly understood the user's question". If
    extraction misread the question, the guard will faithfully confirm that
    the SQL implements the wrong plan and let it through. Plan correctness
    belongs to Gates 3 and 4, not here. This limitation must be stated
    wherever guard results are reported.

DESIGN CONSTRAINTS
    Pure. No FastAPI, no app.py, no database access, no global mutable state,
    no notion of the current user. A plan and a string in, a verdict out - so
    it can be exhaustively tested offline against deliberately mutated SQL.

    Reuses SQLASTParser and SQLASTMetadataExtractor unchanged. It does not
    parse SQL itself and must never grow its own parser.

NOT WIRED IN
    Step 30 changes no execution path. Nothing calls this yet. Wiring it into
    the validation pipeline behind a shadow mode is Step 32.
"""

from ai.ast.exceptions import ASTParserError
from ai.ast.metadata import SQLASTMetadataExtractor
from ai.ast.parser import SQLASTParser

from ai.guard.models import (
    GuardResult,
    Severity,
    Violation,
    ViolationCode,
    resolve_severity,
)
from ai.guard.predicates import (
    ExtractedPredicate,
    extract_aggregate_refs,
    extract_join_conditions,
    extract_predicates,
    extract_row_limit,
    guaranteed_predicates,
    has_always_true_branch,
    has_distinct,
    has_having,
    normalize_identifier,
    normalize_value,
    predicates_for_column,
)


# Operators that mean the same thing when comparing a plan filter against
# SQL. "State1 = 'TN'" and "State1 IN ('TN')" are the same restriction, so
# treating them as different would raise a false violation. This is an exact
# equivalence table, not a similarity judgement.
_OPERATOR_CLASSES = {
    "=": "INCLUDE",
    "IN": "INCLUDE",
    "!=": "EXCLUDE",
    "NOT IN": "EXCLUDE",
}


def _operator_class(operator: str) -> str:
    return _OPERATOR_CLASSES.get(operator, operator)


# Module-level singletons, matching the pattern in ai/sql_validator.py. Both
# are stateless, so sharing them is safe and avoids rebuilding them per call.
_default_parser = SQLASTParser()
_default_extractor = SQLASTMetadataExtractor()


def _hard_failure(
    code: ViolationCode,
    message: str,
    sql: str | None = None,
) -> GuardResult:
    """Build a blocking result carrying a single violation."""

    violation = Violation(
        code=code,
        severity=Severity.HARD_FAILURE,
        message=message,
    )

    return GuardResult(
        passed=False,
        severity=resolve_severity([violation]),
        violations=[violation],
        sql=sql,
    )


def _temporal_columns(plan) -> set:
    """
    Columns the plan expects to be filtered on for time reasons.

    Read from the plan's temporal context so that a legitimate date filter is
    not reported as an unexpected one. Accessed defensively because temporal
    is optional and its shape is owned elsewhere.
    """

    temporal = getattr(plan, "temporal", None)

    if temporal is None:
        return set()

    columns = set()

    date_column = getattr(temporal, "date_column", None)
    if date_column:
        columns.add(normalize_identifier(date_column))

    for name in getattr(temporal, "snapshot_columns", None) or []:
        columns.add(normalize_identifier(name))

    for name in getattr(temporal, "date_columns", None) or []:
        columns.add(normalize_identifier(name))

    default_date = getattr(temporal, "default_date_column", None)
    if default_date:
        columns.add(normalize_identifier(default_date))

    return columns


def _check_metrics(plan, metadata, ast, violations: list) -> None:
    """
    Rules 1 and 2 - the SQL must measure the column the plan named, using the
    arithmetic the plan named.
    """

    # Resolved from the AST rather than from SQLMetadata.aggregates, whose
    # `column` holds the whole inner expression. "SUM(CAST(cy AS DECIMAL))"
    # is reported there as that entire string and would never match "cy",
    # rejecting a query that is perfectly correct.
    aggregates_by_column = {}

    for aggregate in extract_aggregate_refs(ast):
        if aggregate.column is None or aggregate.is_expression:
            continue

        key = normalize_identifier(aggregate.column)
        aggregates_by_column.setdefault(key, []).append(aggregate)

    selected = {
        normalize_identifier(c.name) for c in metadata.selected_columns
    }

    for metric in getattr(plan, "metrics", None) or []:
        expected_column = normalize_identifier(metric.column_name)

        if not expected_column:
            continue

        matching = aggregates_by_column.get(expected_column, [])

        if matching:
            expected_aggregation = (metric.aggregation_type or "").strip().upper()

            # No aggregation recorded on the plan means there is nothing to
            # verify. The guard reports what it can prove, never a guess.
            if not expected_aggregation:
                continue

            actual = {a.function.strip().upper() for a in matching}

            if expected_aggregation not in actual:
                violations.append(
                    Violation(
                        code=ViolationCode.AGGREGATION_MISMATCH,
                        severity=Severity.REPAIRABLE_FAILURE,
                        message=(
                            f"Plan requires {expected_aggregation}"
                            f"({metric.column_name}) but the SQL applies "
                            f"{'/'.join(sorted(actual))} to that column."
                        ),
                        expected=f"{expected_aggregation}({metric.column_name})",
                        actual=(
                            "/".join(
                                f"{f}({metric.column_name})"
                                for f in sorted(actual)
                            )
                        ),
                    )
                )
            continue

        # The plan's metric column is not aggregated anywhere.
        if metadata.aggregates:
            actual_aggregates = "/".join(
                sorted(
                    f"{a.function.upper()}({a.column})"
                    for a in metadata.aggregates
                )
            )

            violations.append(
                Violation(
                    code=ViolationCode.METRIC_MISMATCH,
                    severity=Severity.REPAIRABLE_FAILURE,
                    message=(
                        f"Plan requires the metric '{metric.column_name}' but "
                        f"the SQL aggregates {actual_aggregates} instead."
                    ),
                    expected=metric.column_name,
                    actual=actual_aggregates,
                )
            )
            continue

        if expected_column in selected:
            expected_aggregation = (metric.aggregation_type or "").strip().upper()

            if expected_aggregation:
                violations.append(
                    Violation(
                        code=ViolationCode.AGGREGATION_MISMATCH,
                        severity=Severity.REPAIRABLE_FAILURE,
                        message=(
                            f"Plan requires {expected_aggregation}"
                            f"({metric.column_name}) but the SQL selects that "
                            "column without aggregating it."
                        ),
                        expected=f"{expected_aggregation}({metric.column_name})",
                        actual=metric.column_name,
                    )
                )
            continue

        violations.append(
            Violation(
                code=ViolationCode.MISSING_METRIC,
                severity=Severity.REPAIRABLE_FAILURE,
                message=(
                    f"Plan requires the metric '{metric.column_name}' but it "
                    "does not appear in the SQL at all."
                ),
                expected=metric.column_name,
                actual="not present",
            )
        )


def _check_filters(
    plan,
    predicates: list,
    guaranteed: list,
    violations: list,
) -> None:
    """
    Rules 3, 4 and 5 - every filter the plan requires must be present, on the
    right column, with the right values and a compatible operator.

    Satisfaction is judged against `guaranteed` - the predicates the query
    enforces for every row - rather than every predicate that appears
    somewhere. A filter sitting in an OR branch is written down but not
    enforced, and treating it as satisfied is how
    "WHERE state1 = 'Tamil Nadu' OR 1=1" passed.

    `predicates` (everything present) is still used to report filters the plan
    did not ask for, where appearing at all is what matters.
    """

    expected_columns = set()

    for plan_filter in getattr(plan, "filters", None) or []:
        expected_column = normalize_identifier(plan_filter.column_name)

        if not expected_column:
            continue

        expected_columns.add(expected_column)

        found = predicates_for_column(guaranteed, plan_filter.column_name)

        if not found:
            # Distinguish "absent entirely" from "present but not enforced".
            # The second is the more dangerous case, because the SQL reads as
            # though the filter applies.
            written = predicates_for_column(predicates, plan_filter.column_name)

            if written:
                violations.append(
                    Violation(
                        code=ViolationCode.FILTER_NOT_GUARANTEED,
                        severity=Severity.REPAIRABLE_FAILURE,
                        message=(
                            f"The SQL mentions a filter on "
                            f"'{plan_filter.column_name}' but does not enforce "
                            "it for every row - it sits inside an OR branch or "
                            "under a NOT, so rows can be returned without it "
                            "applying."
                        ),
                        expected=(
                            f"{plan_filter.column_name} enforced for all rows"
                        ),
                        actual="filter present but conditional",
                    )
                )
                continue

            violations.append(
                Violation(
                    code=ViolationCode.MISSING_FILTER,
                    severity=Severity.REPAIRABLE_FAILURE,
                    message=(
                        f"Plan requires a filter on '{plan_filter.column_name}' "
                        f"but the SQL does not filter that column. The query "
                        "answers a broader question than the one asked."
                    ),
                    expected=(
                        f"{plan_filter.column_name} "
                        f"{plan_filter.operator.value} "
                        f"{list(plan_filter.values)}"
                    ),
                    actual="no filter on that column",
                )
            )
            continue

        _check_filter_operator(plan_filter, found, violations)
        _check_filter_values(plan_filter, found, violations)

    _check_unexpected_filters(plan, predicates, expected_columns, violations)


def _check_filter_operator(plan_filter, found: list, violations: list) -> None:
    expected_class = _operator_class(plan_filter.operator.value)
    actual_classes = {_operator_class(p.operator) for p in found}

    if expected_class in actual_classes:
        return

    violations.append(
        Violation(
            code=ViolationCode.FILTER_OPERATOR_MISMATCH,
            severity=Severity.REPAIRABLE_FAILURE,
            message=(
                f"Plan filters '{plan_filter.column_name}' with "
                f"{plan_filter.operator.value} but the SQL uses "
                f"{'/'.join(sorted(p.operator for p in found))}."
            ),
            expected=plan_filter.operator.value,
            actual="/".join(sorted(p.operator for p in found)),
        )
    )


def _check_filter_values(plan_filter, found: list, violations: list) -> None:
    expected_values = {
        normalize_value(v) for v in (plan_filter.values or [])
    }

    if not expected_values:
        return

    actual_values = set()

    for predicate in found:
        for value in predicate.values:
            actual_values.add(normalize_value(value))

    # No literals at all means the filter compares against something the
    # guard cannot read - a parameter or another column. Not verifiable, so
    # not reported as a mismatch.
    if not actual_values:
        return

    if expected_values == actual_values:
        return

    violations.append(
        Violation(
            code=ViolationCode.FILTER_VALUE_MISMATCH,
            severity=Severity.REPAIRABLE_FAILURE,
            message=(
                f"Plan filters '{plan_filter.column_name}' to "
                f"{sorted(str(v) for v in expected_values)} but the SQL "
                f"filters it to {sorted(str(v) for v in actual_values)}. "
                "The result will look reasonable and be wrong."
            ),
            expected=str(sorted(str(v) for v in expected_values)),
            actual=str(sorted(str(v) for v in actual_values)),
        )
    )


def _check_unexpected_filters(
    plan,
    predicates: list,
    expected_columns: set,
    violations: list,
) -> None:
    """
    Filters the plan never asked for change which rows are counted, so they
    are reported as errors rather than notes.

    Predicates comparing two columns are skipped - those are join conditions
    written in the WHERE clause, not filters on a value. Temporal columns are
    skipped because the plan expresses time separately from its filters.
    """

    temporal = _temporal_columns(plan)
    reported = set()

    for predicate in predicates:
        if not predicate.is_value_filter:
            continue

        column = normalize_identifier(predicate.column)

        if column in expected_columns or column in temporal or column in reported:
            continue

        reported.add(column)

        violations.append(
            Violation(
                code=ViolationCode.UNEXPECTED_FILTER,
                severity=Severity.REPAIRABLE_FAILURE,
                message=(
                    f"The SQL filters on '{predicate.column}', which the plan "
                    "did not ask for. This narrows the result set beyond the "
                    "question that was asked."
                ),
                expected="no filter on that column",
                actual=(
                    f"{predicate.column} {predicate.operator} "
                    f"{list(predicate.values)}"
                ),
            )
        )


def _check_extra_selections(plan, metadata, violations: list) -> None:
    """
    Columns selected beyond the plan add output but do not change the rows or
    the figures, so they are reported as notes, never blocks.
    """

    expected = set()

    for metric in getattr(plan, "metrics", None) or []:
        expected.add(normalize_identifier(metric.column_name))

    for dimension in getattr(plan, "dimensions", None) or []:
        expected.add(normalize_identifier(dimension.column_name))

    if not expected:
        return

    for column in metadata.selected_columns:
        name = normalize_identifier(column.name)

        if not name or name == "*" or name in expected:
            continue

        violations.append(
            Violation(
                code=ViolationCode.UNEXPECTED_SELECTION,
                severity=Severity.WARNING,
                message=(
                    f"The SQL selects '{column.name}', which the plan did not "
                    "ask for. This adds a column to the output but does not "
                    "change the figures."
                ),
                expected="not selected",
                actual=column.name,
            )
        )


def _check_grouping(plan, metadata, violations: list) -> None:
    """
    Batch B - the figures must be broken down the way the plan asked.

    Only checked when the SQL aggregates something. Without an aggregate there
    is nothing to group, and a plain SELECT of a dimension is perfectly valid -
    requiring a GROUP BY there would be a false violation.

    Reported as warnings rather than errors. Both a missing and an extra
    grouping do change the figures, so the case for treating them as errors is
    real; the case against is that plan.dimensions comes from a resolver that
    currently passes a minority of its own benchmark. Blocking on it today
    would reject correct SQL generated from an incomplete plan. Shadow mode in
    Step 32 will measure how often that happens before this is promoted.
    """

    dimensions = getattr(plan, "dimensions", None) or []

    if not dimensions or not metadata.aggregates:
        return

    expected = {
        normalize_identifier(d.column_name)
        for d in dimensions
        if d.column_name
    }

    actual = {normalize_identifier(g) for g in metadata.group_by if g}

    for dimension in dimensions:
        name = normalize_identifier(dimension.column_name)

        if not name or name in actual:
            continue

        violations.append(
            Violation(
                code=ViolationCode.MISSING_GROUPING,
                severity=Severity.WARNING,
                message=(
                    f"Plan breaks the figures down by "
                    f"'{dimension.column_name}' but the SQL does not group by "
                    "it, so the totals are aggregated more coarsely than asked."
                ),
                expected=f"GROUP BY {dimension.column_name}",
                actual=(
                    f"GROUP BY {sorted(metadata.group_by)}"
                    if metadata.group_by
                    else "no GROUP BY"
                ),
            )
        )

    for grouping in metadata.group_by:
        name = normalize_identifier(grouping)

        if not name or name in expected:
            continue

        violations.append(
            Violation(
                code=ViolationCode.UNEXPECTED_GROUPING,
                severity=Severity.WARNING,
                message=(
                    f"The SQL groups by '{grouping}', which the plan did not "
                    "ask for. This splits the totals across more rows than "
                    "intended."
                ),
                expected="not grouped by that column",
                actual=f"GROUP BY {grouping}",
            )
        )


def _check_ranking(plan, metadata, ast, violations: list) -> None:
    """
    Batch B - row limit and sort direction.

    Both are exact comparisons against explicit plan fields. When the plan
    records no ranking, nothing here runs at all.
    """

    ranking = getattr(plan, "ranking", None)

    if ranking is None:
        return

    _check_row_limit(ranking, metadata, ast, violations)
    _check_order_direction(ranking, metadata, violations)


def _check_row_limit(ranking, metadata, ast, violations: list) -> None:
    expected = getattr(ranking, "top_n", None)

    if not expected:
        return

    actual = extract_row_limit(ast, metadata)

    if actual is None:
        violations.append(
            Violation(
                code=ViolationCode.MISSING_LIMIT,
                severity=Severity.REPAIRABLE_FAILURE,
                message=(
                    f"Plan asks for the top {expected} rows but the SQL caps "
                    "nothing, so the entire result set is returned."
                ),
                expected=f"TOP {expected}",
                actual="no row limit",
            )
        )
        return

    if actual != expected:
        violations.append(
            Violation(
                code=ViolationCode.LIMIT_MISMATCH,
                severity=Severity.REPAIRABLE_FAILURE,
                message=(
                    f"Plan asks for the top {expected} rows but the SQL "
                    f"returns {actual}."
                ),
                expected=f"TOP {expected}",
                actual=f"TOP {actual}",
            )
        )


def _check_order_direction(ranking, metadata, violations: list) -> None:
    expected_direction = getattr(ranking, "direction", None)

    if expected_direction is None:
        return

    expected = expected_direction.value.strip().upper()

    if not metadata.order_by:
        # A ranking with no ORDER BY is not merely unsorted. TOP N without
        # ORDER BY returns an arbitrary N rows, so the same query can give a
        # different answer each run.
        violations.append(
            Violation(
                code=ViolationCode.MISSING_ORDER_BY,
                severity=Severity.REPAIRABLE_FAILURE,
                message=(
                    f"Plan ranks {expected} but the SQL has no ORDER BY. A row "
                    "limit without an ORDER BY returns an arbitrary set of "
                    "rows, so the answer is not reproducible."
                ),
                expected=f"ORDER BY ... {expected}",
                actual="no ORDER BY",
            )
        )
        return

    # The leading ORDER BY term decides the ranking.
    actual = (metadata.order_by[0].direction or "").strip().upper()

    if actual == expected:
        return

    violations.append(
        Violation(
            code=ViolationCode.ORDER_DIRECTION_MISMATCH,
            severity=Severity.REPAIRABLE_FAILURE,
            message=(
                f"Plan ranks {expected} but the SQL ranks {actual}. This "
                "inverts the answer - the lowest values are presented where "
                "the highest were asked for, or the reverse."
            ),
            expected=f"ORDER BY {metadata.order_by[0].column} {expected}",
            actual=f"ORDER BY {metadata.order_by[0].column} {actual}",
        )
    )


def _check_predicate_integrity(ast, violations: list) -> None:
    """
    A WHERE clause that cannot restrict anything.

    "OR 1=1" and "OR TRUE" make the whole condition true for every row while
    the required filter still appears in the text. Reported as an error
    because no plan ever asks for it.
    """

    if not has_always_true_branch(ast):
        return

    violations.append(
        Violation(
            code=ViolationCode.ALWAYS_TRUE_PREDICATE,
            severity=Severity.REPAIRABLE_FAILURE,
            message=(
                "The WHERE clause contains an OR branch that is true for every "
                "row, so the filters around it restrict nothing and the query "
                "returns the whole table."
            ),
            expected="every OR branch to depend on the data",
            actual="an always-true branch such as 1=1",
        )
    )


def _check_hidden_restrictions(plan, metadata, ast, violations: list) -> None:
    """
    Clauses that quietly change which rows reach the answer.

    HAVING and DISTINCT are reported as notes rather than errors: the plan has
    no field capable of authorising either, so treating them as errors would
    flag every legitimate use - a threshold question the resolver recorded no
    other way, for instance. Recording them keeps them visible without
    rejecting correct work.

    An unrequested row limit is different. It is an error, because the plan
    states explicitly whether a ranking was asked for, and a TOP the plan never
    requested answers a narrower question than the user asked. The prompt does
    not instruct the model to add one, so its presence is the model's own
    invention.
    """

    if has_having(ast):
        violations.append(
            Violation(
                code=ViolationCode.UNEXPECTED_HAVING,
                severity=Severity.WARNING,
                message=(
                    "The SQL applies a HAVING restriction that the plan did "
                    "not request, dropping groups from the result."
                ),
                expected="no HAVING restriction",
                actual="HAVING present",
            )
        )

    if has_distinct(ast):
        violations.append(
            Violation(
                code=ViolationCode.UNEXPECTED_DISTINCT,
                severity=Severity.WARNING,
                message=(
                    "The SQL uses SELECT DISTINCT, which the plan did not "
                    "request. De-duplication can change both the row count and "
                    "the totals."
                ),
                expected="no DISTINCT",
                actual="DISTINCT present",
            )
        )

    ranking = getattr(plan, "ranking", None)

    if ranking is not None and getattr(ranking, "top_n", None):
        return

    limit = extract_row_limit(ast, metadata)

    if limit is None:
        return

    violations.append(
        Violation(
            code=ViolationCode.UNEXPECTED_LIMIT,
            severity=Severity.REPAIRABLE_FAILURE,
            message=(
                f"The SQL returns only {limit} row(s), but the plan did not "
                "ask for a ranking or a limit. The answer would cover part of "
                "the data while appearing to cover all of it."
            ),
            expected="no row limit",
            actual=f"limit of {limit}",
        )
    )


def _build_alias_map(metadata) -> dict:
    """
    Map every alias and table name in the query to its table name, normalised.

    Built here rather than reused from the schema validator, which keeps this
    logic private and lives in a file this module must not modify.
    """

    alias_map = {}

    for table in metadata.tables:
        name = normalize_identifier(table.name)

        if not name:
            continue

        alias_map[name] = name

        if table.alias:
            alias_map[normalize_identifier(table.alias)] = name

    for join in metadata.joins:
        name = normalize_identifier(join.table)

        if not name:
            continue

        alias_map[name] = name

        if join.alias:
            alias_map[normalize_identifier(join.alias)] = name

    return alias_map


def _resolve_table(reference: str | None, alias_map: dict) -> str:
    """Resolve an alias to its table name, or return the reference unchanged."""

    key = normalize_identifier(reference)

    return alias_map.get(key, key)


def _sql_tables(metadata) -> set:
    """Physical tables the query reads, excluding CTE names."""

    ctes = {normalize_identifier(c) for c in metadata.ctes}

    tables = set()

    for table in metadata.tables:
        name = normalize_identifier(table.name)

        if name and name not in ctes:
            tables.add(name)

    for join in metadata.joins:
        name = normalize_identifier(join.table)

        if name and name not in ctes:
            tables.add(name)

    return tables


def _check_joins(plan, metadata, join_conditions: list, violations: list) -> None:
    """
    Batch C - the tables must be connected the way the plan requires.

    Compared against plan.joins rather than the discovered relationship table.
    The relationship service returns rows without filtering on is_confirmed or
    confidence_score, so it mixes verified relationships with auto-discovered
    guesses; validating against it could bless a wrong join or reject a right
    one. The plan states the joins it intends, and that is what conformance
    means here.
    """

    alias_map = _build_alias_map(metadata)

    # Resolve every join condition's endpoints through the alias map once.
    resolved = []

    for condition in join_conditions:
        resolved.append(
            {
                "tables": frozenset(
                    {
                        _resolve_table(condition.left.table, alias_map),
                        _resolve_table(condition.right.table, alias_map),
                    }
                ),
                "endpoints": frozenset(
                    {
                        (
                            _resolve_table(condition.left.table, alias_map),
                            normalize_identifier(condition.left.column),
                        ),
                        (
                            _resolve_table(condition.right.table, alias_map),
                            normalize_identifier(condition.right.column),
                        ),
                    }
                ),
                "condition": condition,
            }
        )

    _check_cartesian(metadata, resolved, violations)

    for plan_join in getattr(plan, "joins", None) or []:
        _check_single_join(plan_join, resolved, violations)

    _check_unexpected_tables(plan, metadata, violations)


def _check_cartesian(metadata, resolved: list, violations: list) -> None:
    """
    Two or more tables with nothing linking them.

    Catches the comma join, the CROSS JOIN and the JOIN with no ON clause in
    one rule, because all three produce the same thing: every row of one table
    paired with every row of the other.

    A HARD_FAILURE rather than a repairable one. It is wrong regardless of
    whether the plan was right, and running it against a large table can take
    the warehouse down.
    """

    tables = _sql_tables(metadata)

    if len(tables) < 2:
        return

    # A join condition only counts if it actually links two different tables.
    linked = set()

    for entry in resolved:
        if len(entry["tables"]) == 2:
            linked |= entry["tables"]

    unlinked = tables - linked

    if not unlinked:
        return

    violations.append(
        Violation(
            code=ViolationCode.CARTESIAN_JOIN,
            severity=Severity.HARD_FAILURE,
            message=(
                f"The query reads {sorted(tables)} but "
                f"{sorted(unlinked)} is not linked by any join condition. "
                "Every row of one table is paired with every row of the "
                "other, which produces a meaningless result and can exhaust "
                "the database."
            ),
            expected="every table linked by a join condition",
            actual=f"unlinked: {sorted(unlinked)}",
        )
    )


def _check_single_join(plan_join, resolved: list, violations: list) -> None:
    """One required join: right tables, right keys."""

    source_table = normalize_identifier(plan_join.source_table)
    target_table = normalize_identifier(plan_join.target_table)

    if not source_table or not target_table:
        return

    expected_tables = frozenset({source_table, target_table})

    expected_endpoints = frozenset(
        {
            (source_table, normalize_identifier(plan_join.source_key)),
            (target_table, normalize_identifier(plan_join.target_key)),
        }
    )

    connecting = [e for e in resolved if e["tables"] == expected_tables]

    if not connecting:
        violations.append(
            Violation(
                code=ViolationCode.JOIN_MISMATCH,
                severity=Severity.REPAIRABLE_FAILURE,
                message=(
                    f"Plan requires '{plan_join.source_table}' to be joined to "
                    f"'{plan_join.target_table}' but the SQL does not join "
                    "those two tables."
                ),
                expected=(
                    f"{plan_join.source_table}.{plan_join.source_key} = "
                    f"{plan_join.target_table}.{plan_join.target_key}"
                ),
                actual=(
                    "joins present: "
                    + str(sorted(sorted(e["tables"]) for e in resolved))
                    if resolved
                    else "no join conditions"
                ),
            )
        )
        return

    if any(e["endpoints"] == expected_endpoints for e in connecting):
        return

    actual = sorted(
        f"{table}.{column}"
        for e in connecting
        for table, column in e["endpoints"]
    )

    violations.append(
        Violation(
            code=ViolationCode.JOIN_KEY_MISMATCH,
            severity=Severity.REPAIRABLE_FAILURE,
            message=(
                f"Plan joins '{plan_join.source_table}' to "
                f"'{plan_join.target_table}' on "
                f"{plan_join.source_key}/{plan_join.target_key}, but the SQL "
                "joins those tables on different columns. The rows will be "
                "paired incorrectly while the result still looks plausible."
            ),
            expected=(
                f"{plan_join.source_table}.{plan_join.source_key} = "
                f"{plan_join.target_table}.{plan_join.target_key}"
            ),
            actual=" = ".join(actual),
        )
    )


def _check_unexpected_tables(plan, metadata, violations: list) -> None:
    """
    Tables the plan never mentioned.

    Only runs when the plan actually declares its tables. A plan that names
    none cannot be used to judge which tables are unexpected, and guessing
    would produce noise.
    """

    declared = set()

    primary = getattr(plan, "primary_table", None)
    if primary:
        declared.add(normalize_identifier(primary))

    for table in getattr(plan, "relevant_tables", None) or []:
        name = normalize_identifier(getattr(table, "table_name", None))
        if name:
            declared.add(name)

    for join in getattr(plan, "joins", None) or []:
        declared.add(normalize_identifier(join.source_table))
        declared.add(normalize_identifier(join.target_table))

    for metric in getattr(plan, "metrics", None) or []:
        name = normalize_identifier(metric.table_name)
        if name:
            declared.add(name)

    for dimension in getattr(plan, "dimensions", None) or []:
        name = normalize_identifier(dimension.table_name)
        if name:
            declared.add(name)

    declared.discard("")

    if not declared:
        return

    for table in sorted(_sql_tables(metadata) - declared):
        violations.append(
            Violation(
                code=ViolationCode.UNEXPECTED_TABLE,
                severity=Severity.WARNING,
                message=(
                    f"The SQL reads '{table}', which the plan does not "
                    "mention."
                ),
                expected=f"one of {sorted(declared)}",
                actual=table,
            )
        )


def verify_sql_against_plan(
    plan,
    sql: str,
    parser: SQLASTParser | None = None,
    extractor: SQLASTMetadataExtractor | None = None,
) -> GuardResult:
    """
    Verify generated SQL against the semantic plan it was generated from.

    Args:
        plan: The SemanticPlan the SQL was generated from. Required - the guard
            refuses rather than passing when there is nothing to compare
            against.
        sql: The generated SQL.
        parser: Optional AST parser override, for tests. Defaults to the shared
            SQLASTParser.
        extractor: Optional metadata extractor override, for tests.

    Returns:
        GuardResult. In Step 30 this is HARD_FAILURE when the SQL is missing,
        blank, unparseable, or when no plan was supplied; PASS otherwise, with
        the extracted SQLMetadata attached for the Step 31 rules to read.
    """

    parser = parser or _default_parser
    extractor = extractor or _default_extractor

    # Fail closed on a missing plan. Returning PASS here would mean the guard
    # silently approves every query on any code path that forgot to pass one -
    # exactly the failure mode the guard exists to prevent.
    if plan is None:
        return _hard_failure(
            ViolationCode.MISSING_PLAN,
            "No semantic plan was supplied, so SQL conformance cannot be "
            "verified. The guard refuses rather than approving by default.",
            sql=sql,
        )

    if sql is None or not sql.strip():
        return _hard_failure(
            ViolationCode.EMPTY_SQL,
            "No SQL was supplied to verify.",
            sql=sql,
        )

    # SQLASTParser raises on a parse failure rather than returning a context
    # with errors populated, so the exception is the signal here. The
    # context.errors check below is kept as a defensive second path, matching
    # how ai/validation_pipeline.py guards the same call.
    try:
        context = parser.parse(sql)
    except ASTParserError as ex:
        return _hard_failure(
            ViolationCode.SQL_PARSE_FAILURE,
            f"Generated SQL could not be parsed: {ex}",
            sql=sql,
        )

    if context.errors:
        return _hard_failure(
            ViolationCode.SQL_PARSE_FAILURE,
            f"Generated SQL could not be parsed: {context.errors[0]}",
            sql=sql,
        )

    if context.ast is None:
        return _hard_failure(
            ViolationCode.SQL_PARSE_FAILURE,
            "Generated SQL produced no abstract syntax tree.",
            sql=sql,
        )

    metadata = extractor.extract(context.ast)
    predicates = extract_predicates(context.ast)

    violations: list[Violation] = []

    # Batch A. Each rule appends its own violations; none of them short-circuit,
    # so one query reports every way it disagrees with the plan rather than
    # only the first. A reviewer fixing SQL needs the whole list.
    _check_metrics(plan, metadata, context.ast, violations)
    _check_filters(
        plan,
        predicates,
        guaranteed_predicates(context.ast),
        violations,
    )
    _check_predicate_integrity(context.ast, violations)
    _check_extra_selections(plan, metadata, violations)
    _check_hidden_restrictions(plan, metadata, context.ast, violations)

    # Batch B.
    _check_grouping(plan, metadata, violations)
    _check_ranking(plan, metadata, context.ast, violations)

    # Batch C.
    _check_joins(
        plan,
        metadata,
        extract_join_conditions(context.ast),
        violations,
    )

    severity = resolve_severity(violations)

    return GuardResult(
        passed=severity in (Severity.PASS, Severity.WARNING),
        severity=severity,
        violations=violations,
        sql=sql,
        serialized_sql=context.serialized_sql,
        metadata=metadata,
    )
