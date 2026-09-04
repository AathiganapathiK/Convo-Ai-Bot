"""
Gate 3 P0 - the runtime's view of Gate 2 configuration.

Gate 2 gave an administrator three switches on the Semantic Control Center:
exclude a column, confirm a meaning, and give a dimension a role. Every one of
them was written to the database and none of them was ever read back by the
code that answers questions. An administrator who excluded a duplicate State
column, or marked a load timestamp as INTERNAL, changed nothing at all about
what the chatbot did. This module is what makes those switches take effect.

WHAT IS FILTERED, AND WHAT DELIBERATELY IS NOT

  is_excluded = 1     hidden everywhere. The administrator said this column
                      must not be offered to business users, and that is the
                      whole purpose of the switch.

  dimension_role      'INTERNAL' is hidden, because the role's own definition
                      in config_schema.py is "exists but is not offered to
                      business users". The other roles are NOT filtered here:
                      IDENTIFIER means "never a grouping", which is a statement
                      about how a column may be used, not about whether it may
                      be seen - an order number is a perfectly good filter. Role
                      is carried through to the plan instead, so Gate 3 Step 17
                      can assign slot roles from it.

  is_confirmed        NOT filtered, on purpose. It is tempting to read "only
                      confirmed configuration is authoritative" as "only query
                      confirmed rows", but the registry holds 20 metrics and 76
                      dimensions of which about ten are confirmed. Filtering on
                      it would switch off almost the entire semantic layer and
                      break the product. Confirmation is a trust signal, and it
                      belongs in confidence scoring (Step 21), not in a WHERE
                      clause. It is exposed here for that later use.

WHY A CAPABILITY PROBE RATHER THAN A PLAIN WHERE CLAUSE

There is no migration runner in this project - backend/migrations/*.sql are
applied by hand, and nothing at startup checks that they were. A database that
has never had 004_semantic_config.sql applied has no is_excluded column at all.
A bare "AND is_excluded = 0" in the resolver would not degrade gracefully on
such a database: it would raise on every single question and take the whole chat
feature down, which is the one part of this product that must not break.

So the columns are probed once per process through SQLAlchemy's inspector -
dialect-agnostic, because the platform database is SQL Server while the tests
run on SQLite fixtures - and the predicate is simply omitted where they are
absent. On an unmigrated database the behaviour is then exactly what it was
before Gate 3: nothing is excluded, because nothing can be.
"""

import logging
from typing import Optional

from sqlalchemy import inspect

from database import engine

logger = logging.getLogger(__name__)


# Probed once per process. A schema change requires a restart to be picked up,
# which is true of a migration anyway.
_column_support: Optional[dict] = None


def _probe() -> dict:
    """
    Which Gate 2 configuration columns actually exist on this database.

    A failure to inspect is treated as "not present". That is the safe
    direction: the query path keeps working with pre-Gate-3 behaviour rather
    than failing closed on every question.
    """
    global _column_support

    if _column_support is not None:
        return _column_support

    support = {
        "metric_is_excluded": False,
        "dimension_is_excluded": False,
        "dimension_role": False,
        "metric_is_confirmed": False,
        "dimension_is_confirmed": False,
    }

    try:
        inspector = inspect(engine)

        metric_columns = {c["name"].lower() for c in inspector.get_columns("semantic_metrics")}
        dimension_columns = {c["name"].lower() for c in inspector.get_columns("semantic_dimensions")}

        support["metric_is_excluded"] = "is_excluded" in metric_columns
        support["metric_is_confirmed"] = "is_confirmed" in metric_columns
        support["dimension_is_excluded"] = "is_excluded" in dimension_columns
        support["dimension_is_confirmed"] = "is_confirmed" in dimension_columns
        support["dimension_role"] = "dimension_role" in dimension_columns

        missing = [name for name, present in support.items() if not present]
        if missing:
            logger.warning(
                "Gate 2 configuration columns absent (%s). Exclusions and "
                "dimension roles will not be applied. Apply "
                "migrations/004_semantic_config.sql to enable them.",
                ", ".join(sorted(missing)),
            )
    except Exception as exc:
        logger.warning(
            "Could not inspect semantic configuration columns (%s); "
            "continuing without exclusion filtering.",
            str(exc).splitlines()[0][:160],
        )

    _column_support = support
    return support


def reset_cache() -> None:
    """Forget the probe. For tests that swap the engine's schema."""
    global _column_support
    _column_support = None


def supports(feature: str) -> bool:
    """Whether one probed column is available."""
    return bool(_probe().get(feature, False))


def metric_filter(alias: str = "") -> str:
    """
    SQL predicate excluding metrics the administrator switched off.

    Returns a fragment beginning with AND, or an empty string when the column
    does not exist. Callers concatenate it into an existing WHERE clause.
    """
    if not supports("metric_is_excluded"):
        return ""

    prefix = f"{alias}." if alias else ""
    return f"AND {prefix}is_excluded = 0"


def dimension_filter(alias: str = "") -> str:
    """
    SQL predicate excluding dimensions the administrator switched off or
    marked INTERNAL.

    dimension_role is compared case-insensitively and NULL is kept: an
    unclassified dimension is not an internal one.
    """
    support = _probe()
    prefix = f"{alias}." if alias else ""

    clauses = []

    if support["dimension_is_excluded"]:
        clauses.append(f"AND {prefix}is_excluded = 0")

    if support["dimension_role"]:
        clauses.append(
            f"AND ({prefix}dimension_role IS NULL "
            f"OR UPPER({prefix}dimension_role) <> 'INTERNAL')"
        )

    return " ".join(clauses)


def dimension_role_column(alias: str = "", label: str = "dimension_role") -> str:
    """
    A SELECT-list expression for dimension_role that is safe on a database
    without the column, so the row shape stays the same either way and callers
    can index it unconditionally.
    """
    if not supports("dimension_role"):
        return f"NULL AS {label}"

    prefix = f"{alias}." if alias else ""
    return f"{prefix}dimension_role AS {label}"


def dimension_confirmed_column(alias: str = "", label: str = "is_confirmed") -> str:
    """
    A SELECT-list expression for is_confirmed, safe on a database without the
    column. Gate 3 Step 21b reads this as the config_trust signal: a dimension a
    person reviewed and approved is stronger evidence than one nobody has looked
    at. Absent, every dimension scores neutral and the other five signals still
    separate candidates.
    """
    if not supports("dimension_is_confirmed"):
        return f"0 AS {label}"

    prefix = f"{alias}." if alias else ""
    return f"{prefix}is_confirmed AS {label}"
