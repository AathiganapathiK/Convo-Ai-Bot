"""
Gate 5 Step 31 - deterministic extraction of filter predicates from a SQL AST.

WHY THIS EXISTS
    SQLMetadata already reports which columns appear in a WHERE clause, but it
    records the predicates themselves as raw strings
    (PredicateInfo.expression = "State1 = 'Tamil Nadu'"). Comparing a plan's
    filter VALUE against a string like that would mean pattern-matching text,
    which breaks on quoting, spacing and capitalisation.

    So this module walks the abstract syntax tree instead and reads the column,
    the operator and the literal values as structured facts. No regular
    expressions, no substring searching, no model of any kind.

WHAT IT DOES NOT DO
    It makes no judgement about whether a predicate is correct. It only reports
    what the SQL says. All comparison happens in plan_conformance.py.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlglot import exp


# sqlglot comparison node -> the operator spelling used by
# semantic_plan.FilterOperator, so plan and SQL are compared in one vocabulary.
_COMPARISON_NODES = {
    exp.EQ: "=",
    exp.NEQ: "!=",
    exp.In: "IN",
    exp.GT: ">",
    exp.GTE: ">=",
    exp.LT: "<",
    exp.LTE: "<=",
    exp.Between: "BETWEEN",
}


@dataclass(frozen=True)
class ExtractedPredicate:
    """
    One filter condition as it actually appears in the generated SQL.

    values is empty when both sides of the comparison are columns - that is a
    join condition written in the WHERE clause, not a filter on a value, and
    callers must not treat it as one.
    """

    column: str
    table: str | None
    operator: str
    values: tuple

    @property
    def is_value_filter(self) -> bool:
        return len(self.values) > 0


def normalize_identifier(name: str | None) -> str:
    """
    Reduce a column reference to a comparable form.

    Strips any table or alias qualifier and lowercases, so that CY, cy, s.CY
    and Sales.CY all compare equal. This is a normalisation, not a guess: it
    removes only qualification and case, never characters that carry meaning.
    """

    if not name:
        return ""

    # Take the final segment, so "Sales.CY" and "s.CY" both reduce to "cy".
    return name.strip().split(".")[-1].strip().strip("[]\"'").lower()


def normalize_value(value):
    """
    Reduce a filter value to a comparable form.

    Strings are lowercased and trimmed, so 'Tamil Nadu' equals 'tamil nadu'.
    Anything that is numerically equal compares equal, so 5, 5.0 and "5" match.

    Deliberately conservative: it does not stem, spell-correct, or treat
    similar-looking values as equivalent. Two genuinely different values must
    never compare equal, because that is precisely the mistake the guard
    exists to catch.
    """

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    text = str(value).strip()

    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return text.lower()


def _literal_values(node) -> tuple:
    """Collect literal values on the right-hand side of a comparison."""

    values = []

    for literal in node.find_all(exp.Literal):
        values.append(literal.this)

    for boolean in node.find_all(exp.Boolean):
        values.append(boolean.this)

    return tuple(values)


def extract_predicates(ast) -> list[ExtractedPredicate]:
    """
    Return every filter predicate in the query's WHERE clause.

    Scoped to WHERE deliberately. Comparisons inside a JOIN ... ON clause are
    join conditions, not filters, and including them would make the guard
    report joins as unexpected filters.
    """

    if ast is None:
        return []

    where = ast.find(exp.Where)

    if where is None:
        return []

    return _predicates_from_node(where)


def _predicates_from_node(scope) -> list:
    """Every comparison predicate beneath one node of the tree."""

    if scope is None:
        return []

    predicates: list[ExtractedPredicate] = []

    for node_type, operator in _COMPARISON_NODES.items():
        for node in scope.find_all(node_type):
            column = node.find(exp.Column)

            if column is None:
                continue

            # A NOT IN is parsed as a Not wrapping an In. Read the negation
            # from the tree rather than assuming.
            resolved_operator = operator

            if operator == "IN" and isinstance(node.parent, exp.Not):
                resolved_operator = "NOT IN"

            if operator == "=" and isinstance(node.parent, exp.Not):
                resolved_operator = "!="

            predicates.append(
                ExtractedPredicate(
                    column=column.name,
                    table=column.table or None,
                    operator=resolved_operator,
                    values=_literal_values(node),
                )
            )

    # IS NULL / IS NOT NULL carry no literal, so they are read separately.
    for node in scope.find_all(exp.Is):
        column = node.find(exp.Column)

        if column is None:
            continue

        if not isinstance(node.expression, exp.Null):
            continue

        predicates.append(
            ExtractedPredicate(
                column=column.name,
                table=column.table or None,
                operator=(
                    "IS NOT NULL"
                    if isinstance(node.parent, exp.Not)
                    else "IS NULL"
                ),
                values=(),
            )
        )

    return predicates


@dataclass(frozen=True)
class JoinEndpoint:
    """One side of a join condition: a column on a table or alias."""

    table: str | None
    column: str


@dataclass(frozen=True)
class JoinCondition:
    """
    One equality linking two tables.

    Stored as an unordered pair conceptually: "a.x = b.y" and "b.y = a.x"
    express the same relationship, so comparison against the plan must not
    depend on which side was written first.
    """

    left: JoinEndpoint
    right: JoinEndpoint

    def endpoints(self) -> frozenset:
        return frozenset(
            {
                (normalize_identifier(self.left.table), normalize_identifier(self.left.column)),
                (normalize_identifier(self.right.table), normalize_identifier(self.right.column)),
            }
        )

    def tables(self) -> frozenset:
        return frozenset(
            {
                normalize_identifier(self.left.table),
                normalize_identifier(self.right.table),
            }
        )


def extract_join_conditions(ast) -> list[JoinCondition]:
    """
    Every equality that links two columns, from JOIN ... ON and from WHERE.

    WHERE is included deliberately. "FROM A, B WHERE A.k = B.k" is an ordinary
    join written in the older style: SQLMetadata reports no join columns for it,
    so reading only the ON clauses would make that query look like a Cartesian
    product and raise a false violation.

    Only column-to-column equalities count. "A.k = 5" is a filter, not a join.
    """

    if ast is None:
        return []

    conditions: list[JoinCondition] = []
    seen = set()

    def collect(scope):
        if scope is None:
            return

        for equality in scope.find_all(exp.EQ):
            columns = list(equality.find_all(exp.Column))

            if len(columns) != 2:
                continue

            condition = JoinCondition(
                left=JoinEndpoint(columns[0].table or None, columns[0].name),
                right=JoinEndpoint(columns[1].table or None, columns[1].name),
            )

            key = condition.endpoints()

            if key in seen:
                continue

            seen.add(key)
            conditions.append(condition)

    for join in ast.find_all(exp.Join):
        collect(join.args.get("on"))

    collect(ast.find(exp.Where))

    return conditions


# Functions that wrap a column without changing which metric is being
# measured. SUM(CAST(cy AS DECIMAL)) and SUM(ISNULL(cy, 0)) both total cy -
# SUM ignores NULLs, so the COALESCE changes nothing about the result.
#
# Arithmetic is deliberately NOT in this list: SUM(cy - py) is a variance, a
# different quantity from SUM(cy), and must not be accepted in its place.
_TRANSPARENT_WRAPPERS = (exp.Cast, exp.TryCast, exp.Coalesce, exp.Round)


@dataclass(frozen=True)
class AggregateRef:
    """
    One aggregate in the query, resolved to the column it actually measures.

    column is None when the aggregate is over an expression that cannot be
    reduced to a single column, which is itself meaningful - it means the SQL
    is not measuring a plain column.
    """

    function: str
    column: str | None
    is_expression: bool


def _unwrap_transparent(node):
    """Strip parentheses and value-preserving wrappers from an expression."""

    while node is not None:
        if isinstance(node, exp.Paren):
            node = node.this
            continue

        if isinstance(node, _TRANSPARENT_WRAPPERS):
            node = node.this
            continue

        break

    return node


def extract_aggregate_refs(ast) -> list:
    """
    Every aggregate, with the column it measures resolved structurally.

    Reads the AST rather than the rendered expression text. SQLMetadata records
    an aggregate's column as the whole inner expression, so
    "SUM(CAST(cy AS DECIMAL(18,2)))" is reported as that entire string and
    never matches the plan's "cy". Unwrapping the node tree instead identifies
    the real column, without resorting to substring matching.
    """

    if ast is None:
        return []

    refs = []

    for aggregate in ast.find_all(exp.AggFunc):
        function = type(aggregate).__name__.upper()

        inner = _unwrap_transparent(aggregate.this)

        if isinstance(inner, exp.Column):
            refs.append(AggregateRef(function, inner.name, False))
            continue

        # An expression rather than a column - arithmetic, a CASE, a literal.
        columns = [c.name for c in aggregate.find_all(exp.Column)]

        refs.append(
            AggregateRef(
                function,
                columns[0] if len(columns) == 1 else None,
                True,
            )
        )

    return refs


def _is_always_true(node) -> bool:
    """
    A predicate that is true regardless of the data.

    Recognises the literal forms that defeat a WHERE clause - "1=1", "TRUE" -
    without attempting general logical evaluation.
    """

    node = _unwrap_transparent(node)

    if isinstance(node, exp.Boolean):
        return bool(node.this)

    if isinstance(node, exp.EQ):
        left, right = node.this, node.expression

        if isinstance(left, exp.Literal) and isinstance(right, exp.Literal):
            return str(left.this) == str(right.this)

    return False


def has_always_true_branch(ast) -> bool:
    """
    Whether any OR in the WHERE clause has a branch that is always true.

    "WHERE state1 = 'Tamil Nadu' OR 1=1" returns every row: the required
    filter is present in the text but guarantees nothing.
    """

    if ast is None:
        return False

    where = ast.find(exp.Where)

    if where is None:
        return False

    for node in where.find_all(exp.Or):
        if _is_always_true(node.this) or _is_always_true(node.expression):
            return True

    return False


def guaranteed_predicates(ast) -> list:
    """
    Predicates the query guarantees for every returned row.

    Only conditions joined by AND at the top level of the WHERE clause hold for
    all rows. A predicate inside an OR branch may not apply, and one inside a
    NOT is inverted, so neither counts as satisfying a required filter.

    This is what separates "the filter appears in the SQL" from "the filter is
    enforced by the SQL".
    """

    if ast is None:
        return []

    where = ast.find(exp.Where)

    if where is None:
        return []

    conjuncts = []

    def descend(node):
        if node is None:
            return

        if isinstance(node, exp.Paren):
            descend(node.this)
            return

        if isinstance(node, exp.And):
            descend(node.this)
            descend(node.expression)
            return

        # Or / Not / anything else: everything beneath it is conditional, so
        # nothing inside can be treated as guaranteed.
        conjuncts.append(node)

    descend(where.this)

    predicates = []

    for conjunct in conjuncts:
        if isinstance(conjunct, (exp.Or, exp.Not)):
            continue

        predicates.extend(_predicates_from_node(conjunct))

    return predicates


def has_having(ast) -> bool:
    return ast is not None and ast.find(exp.Having) is not None


def has_distinct(ast) -> bool:
    if ast is None:
        return False

    select = ast.find(exp.Select)

    return bool(select and select.args.get("distinct"))


def extract_row_limit(ast, metadata) -> int | None:
    """
    The number of rows the query restricts itself to, or None.

    SQLMetadata.limit reads TOP n, but T-SQL can also cap rows with
    OFFSET ... FETCH NEXT n ROWS ONLY, which the extractor records as None.
    Relying on metadata.limit alone would make a FETCH query look unlimited
    and raise a false violation, so the Fetch node is read directly as a
    fallback.
    """

    if metadata is not None and metadata.limit is not None:
        return metadata.limit

    if ast is None:
        return None

    fetch = ast.find(exp.Fetch)

    if fetch is None:
        return None

    count = fetch.args.get("count")

    if count is None:
        return None

    # count may be a literal node or a plain value depending on dialect.
    raw = getattr(count, "this", count)

    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return None


def predicates_for_column(
    predicates: list[ExtractedPredicate],
    column_name: str,
) -> list[ExtractedPredicate]:
    """Every predicate acting on the given column, compared normalised."""

    target = normalize_identifier(column_name)

    return [
        p for p in predicates
        if normalize_identifier(p.column) == target
    ]
