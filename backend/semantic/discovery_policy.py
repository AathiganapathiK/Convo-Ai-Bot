"""
Gate 2 Step 12 - the rules auto-discovery must obey now that configuration exists.

Discovery used to be the only opinion about what a column meant. It is not any
more: an administrator confirms meanings, excludes columns, and names a table's
business date. This module is where discovery learns to defer to that, and
where its worst guesses are replaced with evidence.

WHAT IT CHANGES, AND WHY EACH ONE MATTERED

1. Confirmed rows are untouchable. Discovery's metric UPDATE reset
   aggregation_type unconditionally, and its prune deleted any AUTO row it no
   longer recognised. Confirmations are written onto those same AUTO rows, so a
   re-run could silently undo Step 13's work. This is the reason the whole
   module exists; the rest is quality.

2. Excluded columns stay out. An administrator who excluded a column has said
   it must not be offered to business users. Re-registering it on the next run
   makes that decision meaningless.

3. Only a table's CONFIGURED business date column gets grain expansion.
   Expanding a date into year/quarter/month/week/day is genuinely useful for a
   real transaction date and pure noise for anything else. Discovery expanded
   every date-typed column, so six date columns produced thirty-six dimensions,
   thirty of them redundant - a quarter of the entire registry. There is no
   date-type fallback here on purpose: if nobody has said which column is the
   business date, guessing is what produced the noise.

4. Metrics are judged on evidence first. The old test was "numeric, and the
   name avoids id/key/code" - so DocMonth, Sno, OrderNo and Docnum all became
   measures. Summing them is meaningless.

   The evidence says a single threshold cannot work:

       ID       2,238,958 distinct of 2,238,958 rows   100.0% unique
       OrderNo     29,188 distinct of    36,617 rows    79.7% unique
       Docnum      55,133 distinct of    95,613 rows    57.7% unique
       Sno             13 distinct of 2,238,958 rows     0.0% unique
       DocMonth        12 distinct of 2,238,958 rows     0.0% unique

   A uniqueness rule catches ID and misses the rest. A low-cardinality rule
   catches Sno and DocMonth and misses ID. So both are used, plus a
   TOKEN-based name check for the identifier words - token, not substring,
   because "Nodays" (a real measure) contains "no" and must survive.

5. The table name no longer decides a column's category. detect_semantic_category
   tokenised the table name and the column name into one set. The table is
   QB_MDJMD_SALES_5YRS_SUMMARY, so "sales" was in every column's tokens, and
   Finance matched before Document, Customer or Identifier - which is why
   ProdGrp1-4, MktType, RMNAME, STG and KeyLine all came back Finance. A
   column's category is a fact about the column.

6. Equivalent columns are PROPOSED, never auto-resolved. Which of State1,
   State2, State3 and StateCode to keep is a business decision.
"""

import json
import logging
import re
from typing import Dict, Optional, Set, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)


# Identifier words, matched as whole tokens after camel/snake splitting.
# Substring matching is what makes this dangerous: "no" appears inside
# "Nodays", which is a genuine measure on the receivables table.
IDENTIFIER_TOKENS = {
    "id", "ids", "key", "no", "nos", "num", "number", "sno", "srno", "seq",
    "sequence", "code", "ref", "reference", "guid", "uuid", "docnum", "orderno",
}

# At or above this share of distinct values, a numeric column is an identifier
# rather than something worth summing.
IDENTIFIER_UNIQUENESS = 0.95

# A numeric column with no more than this many distinct values, spread over a
# table far larger, is a code or a label - a month number, a serial group -
# not a quantity. 31 covers day-of-month; months and small code sets sit well
# under it.
LABEL_MAX_DISTINCT = 31

# ...but only when the table is big enough for that to mean something. On a
# thirty-row table, thirty distinct values is just a small table.
LABEL_MAX_UNIQUENESS = 0.01

# A column with one value in every row cannot group anything. It is a load
# stamp or a constant, and it is not a dimension.
CONSTANT_DISTINCT = 1

# Ceiling for the duplicate-column scan. Above this a column is a name or an
# identifier: too expensive to compare, and its values are not ours to read.
DUPLICATE_SCAN_MAX_DISTINCT = 200

# Two columns whose value sets overlap at least this much are worth a human
# deciding between.
DUPLICATE_SIMILARITY = 0.90

# Never read values from a column that may name a person, whatever its
# cardinality. Mirrors ConfigSuggester.PERSONAL_NAME_PATTERNS.
PERSONAL_NAME_PATTERNS = (
    "name", "person", "employee", "staff", "contact", "customer", "party",
    "email", "mail", "phone", "mobile", "address", "user", "owner",
)

SEMANTIC_PATTERNS = {
    "Geography": {
        "region", "country", "state", "city", "territory", "postal", "address", "location"
    },
    "Time": {
        "date", "time", "month", "year", "quarter", "day", "week", "calendar", "period"
    },
    "Organization": {
        "company", "department", "division", "organization", "org", "store", "branch"
    },
    "Product": {
        "product", "item", "sku", "category", "subcategory", "model", "brand", "color", "size"
    },
    "Finance": {
        "sales", "revenue", "cost", "price", "amount", "profit", "tax", "margin", "budget", "finance"
    },
    "Document": {
        "order", "invoice", "document", "receipt", "contract", "number", "code"
    },
    "Customer": {
        "customer", "client", "buyer", "subscriber"
    },
    "Human Resources": {
        "employee", "salesperson", "manager", "staff", "user", "role", "salary", "hire"
    },
    "Identifier": {
        "id", "key", "code", "guid", "uuid"
    },
}


def tokenize(name: str) -> Set[str]:
    """Split camelCase, snake_case and punctuation into lowercase tokens."""
    if not name:
        return set()

    tokens = set()
    for chunk in re.findall(r"[a-zA-Z0-9]+", name):
        for part in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z0-9]|\b)", chunk):
            tokens.add(part.lower())
    return tokens


# Every value this code is capable of producing. Anything stored outside this
# set was written by a person or another system, and must not be recomputed.
OWN_CATEGORIES = set(SEMANTIC_PATTERNS) | {"Other", "UNKNOWN"}


def is_own_category(value) -> bool:
    """
    Did discovery write this category, or did somebody else?

    This is what lets a stale category be corrected without trampling a manual
    one. "Finance" is a value this code produces, so a stored "Finance" may
    well be the old table-name-polluted rule's work and is safe to recompute.
    "LOCATION_COUNTRY" is not in our vocabulary, so a person chose it and it
    stays, whether or not they went on to press Confirm.
    """
    return value is None or value in OWN_CATEGORIES


def detect_semantic_category(column_name: str, data_type: str = None) -> str:
    """
    A column's category, decided from the COLUMN name only.

    The table name is deliberately not consulted. See point 5 in the module
    docstring: including it made every column of a table called ...SALES...
    into Finance. Returning "Other" when the column name says nothing is the
    honest answer, and better than a confident wrong one - an administrator can
    see "Other" and fix it, whereas "Finance" looks already decided.
    """
    tokens = tokenize(column_name)

    for category, patterns in SEMANTIC_PATTERNS.items():
        for pattern in patterns:
            if len(pattern) <= 3:
                if pattern in tokens:
                    return category
            elif any(pattern in token for token in tokens):
                return category

    return "Other"


class DiscoveryPolicy:
    """
    Everything discovery needs to know before it registers anything.

    Loaded once per run: confirmed rows, exclusions, configured date and month
    columns, and the profiling evidence already gathered by the suggester.
    """

    def __init__(self, connection_id: str):
        self.connection_id = connection_id
        self.confirmed_metrics: Set[Tuple[str, str]] = set()
        self.confirmed_dimensions: Set[Tuple[str, str, str]] = set()
        self.excluded_columns: Set[Tuple[str, str]] = set()
        self.date_columns: Dict[str, str] = {}          # table -> business date column
        self.period_label_columns: Set[Tuple[str, str]] = set()
        self.evidence: Dict[Tuple[str, str], dict] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @staticmethod
    def _rows(conn, sql, params, what):
        """
        Run one lookup, and treat an unavailable one as "nothing configured".

        Each query is guarded separately and on purpose. Migration 004 added
        is_confirmed, is_excluded and semantic_table_config; a database that
        has not had it applied - or an in-memory schema in a test - would
        otherwise fail the whole discovery run. Degrading to the pre-Step-12
        behaviour is the safe direction: with no confirmations recorded there
        are none to protect.
        """
        try:
            return list(conn.execute(text(sql), params))
        except Exception as exc:
            logger.warning(
                "Discovery policy could not read %s (%s); continuing without it.",
                what, str(exc).splitlines()[0][:120],
            )
            return []

    @classmethod
    def load(cls, connection_id: str, conn) -> "DiscoveryPolicy":
        policy = cls(connection_id)
        params = {"connection_id": connection_id}

        for table, column in cls._rows(conn, """
            SELECT table_name, column_name FROM semantic_metrics
            WHERE connection_id = :connection_id AND is_confirmed = 1
        """, params, "confirmed metrics"):
            policy.confirmed_metrics.add((_l(table), _l(column)))

        for table, column, dim_name in cls._rows(conn, """
            SELECT table_name, column_name, dimension_name FROM semantic_dimensions
            WHERE connection_id = :connection_id AND is_confirmed = 1
        """, params, "confirmed dimensions"):
            policy.confirmed_dimensions.add((_l(table), _l(column), _l(dim_name)))

        for source in ("semantic_metrics", "semantic_dimensions"):
            for table, column in cls._rows(
                conn,
                "SELECT table_name, column_name FROM %s "
                "WHERE connection_id = :connection_id AND is_excluded = 1" % source,
                params, "exclusions on %s" % source,
            ):
                policy.excluded_columns.add((_l(table), _l(column)))

        for table, date_col, month_col, sort_col in cls._rows(conn, """
            SELECT table_name, date_column, month_column, month_sort_column
            FROM semantic_table_config WHERE connection_id = :connection_id
        """, params, "table configuration"):
            if date_col:
                policy.date_columns[_l(table)] = date_col
            for column in (date_col, month_col, sort_col):
                if column:
                    policy.period_label_columns.add((_l(table), _l(column)))

        # Profiling already paid for by the suggester: cardinality, row counts
        # and, for high-cardinality numerics, min/max/avg. Discovery reuses it
        # rather than re-scanning millions of rows on every connection
        # activation.
        for table, column, distinct, rows, samples, data_type in cls._rows(conn, """
            SELECT table_name, column_name, distinct_count, row_count_profiled,
                   sample_values, data_type
            FROM semantic_suggestion_evidence
            WHERE connection_id = :connection_id AND column_name IS NOT NULL
        """, params, "profiling evidence"):
            policy.evidence[(_l(table), _l(column))] = {
                "distinct_count": distinct,
                "row_count": rows,
                "samples": _load_samples(samples),
                "data_type": data_type,
            }

        logger.info(
            "Discovery policy: %d confirmed metrics, %d confirmed dimensions, "
            "%d excluded columns, %d configured date columns, %d profiled columns.",
            len(policy.confirmed_metrics), len(policy.confirmed_dimensions),
            len(policy.excluded_columns), len(policy.date_columns), len(policy.evidence),
        )
        return policy

    # ------------------------------------------------------------------
    # What discovery asks
    # ------------------------------------------------------------------

    def is_confirmed_metric(self, table: str, column: str) -> bool:
        return (_l(table), _l(column)) in self.confirmed_metrics

    def is_confirmed_dimension(self, table: str, column: str, dimension_name: str) -> bool:
        return (_l(table), _l(column), _l(dimension_name)) in self.confirmed_dimensions

    def is_excluded(self, table: str, column: str) -> bool:
        return (_l(table), _l(column)) in self.excluded_columns

    def should_expand_date(self, table: str, column: str) -> bool:
        """
        True only for the column configured as this table's business date.

        No fallback to "it looks like a date". That fallback is what turned
        createddate - one distinct value across 2.2 million rows, an ETL load
        stamp - into six analytical dimensions.
        """
        configured = self.date_columns.get(_l(table))
        return bool(configured) and _l(configured) == _l(column)

    def is_constant_column(self, table: str, column: str) -> bool:
        """One value in every row: nothing to group by, nothing to measure."""
        ev = self.evidence.get((_l(table), _l(column)))
        if not ev or ev.get("distinct_count") is None:
            return False
        return ev["distinct_count"] <= CONSTANT_DISTINCT and (ev.get("row_count") or 0) > 1

    def rejects_as_metric(self, table: str, column: str) -> Optional[str]:
        """
        Why this numeric column is not a measure, or None if it is one.

        Evidence first, name second. The returned string is a reason, so a log
        line or a future review screen can say what was decided and why.
        """
        key = (_l(table), _l(column))

        if key in self.period_label_columns:
            return (
                "configured as this table's date, month or month-sort column, "
                "so it labels a period rather than measuring one"
            )

        ev = self.evidence.get(key)

        if ev and ev.get("distinct_count") is not None and (ev.get("row_count") or 0) > 0:
            distinct = ev["distinct_count"]
            rows = ev["row_count"]
            uniqueness = distinct / rows

            if uniqueness >= IDENTIFIER_UNIQUENESS:
                return (
                    "%.1f%% of rows hold a distinct value, so it identifies rows "
                    "rather than measuring them" % (uniqueness * 100)
                )

            if distinct <= LABEL_MAX_DISTINCT and uniqueness <= LABEL_MAX_UNIQUENESS:
                return (
                    "only %d distinct values across %d rows, which is a code or a "
                    "label rather than a quantity" % (distinct, rows)
                )

        # Name evidence is a secondary signal, and token-based so that a
        # measure like "Nodays" is not rejected for containing "no".
        identifier_tokens = tokenize(column) & IDENTIFIER_TOKENS
        if identifier_tokens:
            return (
                "the name contains the identifier token '%s'"
                % sorted(identifier_tokens)[0]
            )

        return None


def _l(value) -> str:
    return (value or "").lower()


def _load_samples(raw):
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


# ---------------------------------------------------------------------------
# Requirement 6 - equivalent columns are proposed, never resolved
# ---------------------------------------------------------------------------

def find_equivalent_columns(connection_id, platform_conn, source_engine):
    """
    Columns in the same table whose values are the same, or one inside another.

    Reports; never acts. Which of State1, State2, State3 and StateCode to keep
    is a business decision - they are not interchangeable even when their
    values overlap completely, because one of them may be the column the
    business actually means. Auto-excluding the "duplicates" would be picking a
    winner by row order.

    Bounded on purpose:
      * only low-cardinality columns, so the comparison is cheap
      * never a column whose name suggests it identifies a person, whatever its
        cardinality - the same gate the suggester applies
      * value SETS are compared in memory and never returned, so nothing here
        can leak a value into a log or a report
    """
    candidates = {}

    for table, column, distinct, data_type in platform_conn.execute(text("""
        SELECT table_name, column_name, distinct_count, data_type
        FROM semantic_suggestion_evidence
        WHERE connection_id = :connection_id
          AND column_name IS NOT NULL
          AND distinct_count IS NOT NULL
    """), {"connection_id": connection_id}):
        if distinct is None or distinct < 2 or distinct > DUPLICATE_SCAN_MAX_DISTINCT:
            continue
        if any(p in (column or "").lower() for p in PERSONAL_NAME_PATTERNS):
            continue
        candidates.setdefault(table, []).append((column, distinct))

    findings = []

    for table, columns in candidates.items():
        values = {}
        for column, _distinct in columns:
            try:
                with source_engine.connect() as sc:
                    values[column] = {
                        str(r[0]) for r in sc.execute(text(
                            "SELECT DISTINCT [%s] FROM [%s] WHERE [%s] IS NOT NULL"
                            % (column, table, column)
                        ))
                    }
            except Exception as exc:
                logger.debug("Could not read %s.%s: %s", table, column, exc)

        names = sorted(values)
        for i, left in enumerate(names):
            for right in names[i + 1:]:
                a, b = values[left], values[right]
                if not a or not b:
                    continue

                union = len(a | b)
                overlap = len(a & b)
                jaccard = overlap / union if union else 0.0
                smaller = min(len(a), len(b))
                containment = overlap / smaller if smaller else 0.0

                if jaccard >= DUPLICATE_SIMILARITY:
                    relation = "identical"
                elif containment >= 0.99:
                    relation = "contained"
                else:
                    continue

                findings.append({
                    "table_name": table,
                    "columns": [left, right],
                    "relation": relation,
                    "distinct": [len(a), len(b)],
                    "overlap": overlap,
                    "jaccard": round(jaccard, 3),
                    "proposal": (
                        "These two columns hold the same values. Decide which one "
                        "the business means and exclude the other."
                        if relation == "identical" else
                        "Every value of the smaller column also appears in the "
                        "larger one. It may be a narrower copy - confirm which "
                        "the business means."
                    ),
                })

    return sorted(findings, key=lambda f: (f["table_name"], f["columns"]))
