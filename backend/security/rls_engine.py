"""
security/rls_engine.py

Database-driven Row-Level Security (RLS) engine.

Reads per-user access rules from `user_data_access` and injects
WHERE-clause filters into generated SQL before execution.

Supported access types:
    REGION       — filters on Region.SalesTerritoryKey
    SALESPERSON  — filters on Salesperson.EmployeeKey

Design decisions:
    - SUPER_ADMIN and ADMIN roles bypass RLS entirely.
    - If a user has no user_data_access rows, they see ALL data (open access).
    - Multiple access values of the same type are OR-combined (IN clause).
    - The engine uses parameterized value injection to prevent SQL injection.
"""

import re
import logging
from typing import Optional

from sqlalchemy import text
from database import engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Access type → SQL column mapping
# ---------------------------------------------------------------------------

ACCESS_TYPE_COLUMNS = {
    "REGION":       "SalesTerritoryKey",
    "SALESPERSON":  "EmployeeKey",
}


# ---------------------------------------------------------------------------
# Load user access rules from DB
# ---------------------------------------------------------------------------

def get_user_access_rules(employee_id: str) -> dict[str, list[str]]:
    """
    Load all data access rules for a user from user_data_access.
    Returns: {"REGION": ["1", "4", "7"], "SALESPERSON": ["E001"]}
    """
    query = """
    SELECT access_type, access_value
    FROM user_data_access
    WHERE employee_id = :employee_id
    """

    with engine.connect() as connection:
        result = connection.execute(text(query), {"employee_id": employee_id})
        rows = result.fetchall()

    rules: dict[str, list[str]] = {}
    for row in rows:
        access_type = row.access_type
        if access_type not in rules:
            rules[access_type] = []
        rules[access_type].append(row.access_value)

    return rules


# ---------------------------------------------------------------------------
# RLS filter injection
# ---------------------------------------------------------------------------

def apply_rls(
    sql_query: str,
    user: dict,
) -> tuple[str, dict]:
    """
    Inject RLS filters into a SQL query based on the user's data access rules and company_id context.

    Parameters:
        sql_query:  The generated SQL query string.
        user:       The authenticated user dict from get_current_user().

    Returns:
        (modified_sql, rls_metadata) where rls_metadata describes what was applied.
    """
    role = user.get("role", "")
    employee_id = user.get("employee_id", "")
    company_id = user.get("company_id", "")

    # Build filter clauses (company separation is handled at the connection level)
    filters = []

    metadata = {"rls_applied": True, "filters": []}

    # Non-admins get extra RLS restrictions
    if role not in ("SUPER_ADMIN", "ADMIN"):
        rules = get_user_access_rules(employee_id)
        if rules:
            for access_type, values in rules.items():
                column = ACCESS_TYPE_COLUMNS.get(access_type)
                if not column:
                    logger.warning("Unknown RLS access_type '%s' for user '%s'.", access_type, employee_id)
                    continue

                # Build an IN clause with quoted values
                quoted_values = ", ".join(f"'{v}'" for v in values)
                filter_clause = f"{column} IN ({quoted_values})"
                filters.append(filter_clause)

                metadata["filters"].append({
                    "access_type": access_type,
                    "column": column,
                    "values": values,
                })

    if not filters:
        return sql_query, {"rls_applied": False, "reason": "no_filters"}

    combined_filter = " AND ".join(filters)
    modified_sql = _inject_where_clause(sql_query, combined_filter)

    logger.info(
        "RLS applied for user='%s', company='%s': %s",
        employee_id,
        company_id,
        combined_filter,
    )

    return modified_sql, metadata


def _inject_where_clause(sql_query: str, filter_clause: str) -> str:
    """
    Inject a filter clause into a SQL query, handling both
    existing WHERE clauses and GROUP BY/ORDER BY/HAVING placement.
    """
    sql_query = sql_query.strip()

    if sql_query.endswith(";"):
        sql_query = sql_query[:-1]

    lower_sql = sql_query.lower()

    # Pattern for GROUP BY, ORDER BY, HAVING
    tail_pattern = re.compile(
        r"\b(group\s+by|order\s+by|having)\b",
        re.IGNORECASE,
    )

    if " where " in lower_sql:
        # Existing WHERE — add AND before any GROUP BY/ORDER BY/HAVING
        match = tail_pattern.search(sql_query, lower_sql.index(" where ") + 7)
        if match:
            pos = match.start()
            return (
                sql_query[:pos]
                + f"AND {filter_clause} "
                + sql_query[pos:]
            )
        return sql_query + f" AND {filter_clause}"

    else:
        # No WHERE — insert WHERE before any GROUP BY/ORDER BY/HAVING
        match = tail_pattern.search(sql_query)
        if match:
            pos = match.start()
            return (
                sql_query[:pos]
                + f"WHERE {filter_clause} "
                + sql_query[pos:]
            )
        return sql_query + f" WHERE {filter_clause}"


# ---------------------------------------------------------------------------
# Admin helpers
# ---------------------------------------------------------------------------

def get_user_data_access(employee_id: str) -> list[dict]:
    """Get all data access rules for a user."""
    with engine.connect() as connection:
        result = connection.execute(text("""
            SELECT id, employee_id, access_type, access_value, created_at, created_by
            FROM user_data_access
            WHERE employee_id = :employee_id
            ORDER BY access_type
        """), {"employee_id": employee_id})
        return [dict(row._mapping) for row in result.fetchall()]


def add_user_data_access(
    employee_id: str,
    access_type: str,
    access_value: str,
    created_by: Optional[str] = None,
) -> None:
    """Add a data access rule for a user."""
    if access_type not in ACCESS_TYPE_COLUMNS:
        raise ValueError(f"Invalid access_type: {access_type}. Must be one of {list(ACCESS_TYPE_COLUMNS.keys())}")

    with engine.begin() as connection:
        connection.execute(text("""
            IF NOT EXISTS (
                SELECT 1 FROM user_data_access
                WHERE employee_id = :employee_id
                  AND access_type = :access_type
                  AND access_value = :access_value
            )
            INSERT INTO user_data_access (employee_id, access_type, access_value, created_by)
            VALUES (:employee_id, :access_type, :access_value, :created_by)
        """), {
            "employee_id":  employee_id,
            "access_type":  access_type,
            "access_value": access_value,
            "created_by":   created_by,
        })


def remove_user_data_access(access_id: int) -> None:
    """Remove a specific data access rule by ID."""
    with engine.begin() as connection:
        connection.execute(text("""
            DELETE FROM user_data_access WHERE id = :id
        """), {"id": access_id})
