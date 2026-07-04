"""
security/cls_engine.py

Database-driven Column-Level Security (CLS) engine.

Reads per-role column access rules from `role_column_access` and:
    1. Validates that a generated SQL query only references allowed columns.
    2. Filters result-set dictionaries to remove unauthorized columns.

Design decisions:
    - Roles with NO entries in role_column_access have FULL access (SUPER_ADMIN, ADMIN).
    - Only columns explicitly marked is_allowed=1 are permitted for restricted roles.
    - Columns marked is_allowed=0 are explicitly forbidden.
    - CLS validation runs BEFORE query execution (block forbidden queries).
    - CLS filtering runs AFTER query execution (strip unauthorized columns from results).
"""

import logging
from typing import Optional
from sqlalchemy import text
from database import engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Load CLS rules from database
# ---------------------------------------------------------------------------

def _get_role_id(role_name: str) -> Optional[int]:
    """Look up the role ID from the role name."""
    with engine.connect() as connection:
        result = connection.execute(text("""
            SELECT id FROM roles WHERE role_name = :role_name
        """), {"role_name": role_name})
        row = result.fetchone()
        return row.id if row else None


def get_role_column_rules(role_name: str) -> dict[str, dict[str, bool]]:
    """
    Load all column access rules for a role.
    Returns: {"Sales": {"OrderDate": True, "Cost": False}, ...}
    """
    role_id = _get_role_id(role_name)
    if role_id is None:
        return {}

    with engine.connect() as connection:
        result = connection.execute(text("""
            SELECT table_name, column_name, is_allowed
            FROM role_column_access
            WHERE role_id = :role_id
        """), {"role_id": role_id})
        rows = result.fetchall()

    if not rows:
        # No CLS rules = full access
        return {}

    rules: dict[str, dict[str, bool]] = {}
    for row in rows:
        table = row.table_name
        if table not in rules:
            rules[table] = {}
        rules[table][row.column_name] = bool(row.is_allowed)

    return rules


def get_forbidden_columns(role_name: str) -> list[str]:
    """
    Return a flat list of column names that are explicitly forbidden
    for this role (is_allowed=0).
    """
    rules = get_role_column_rules(role_name)
    forbidden = []
    for table, columns in rules.items():
        for col, allowed in columns.items():
            if not allowed:
                forbidden.append(col)
    return forbidden


def get_allowed_columns(role_name: str, table_name: str) -> Optional[list[str]]:
    """
    Return the list of allowed column names for a role on a specific table.
    Returns None if the role has full access (no restrictions).
    """
    rules = get_role_column_rules(role_name)

    if not rules:
        return None  # Full access

    table_rules = rules.get(table_name)
    if table_rules is None:
        return None  # No restrictions on this table

    return [col for col, allowed in table_rules.items() if allowed]


# ---------------------------------------------------------------------------
# CLS validation (pre-execution)
# ---------------------------------------------------------------------------

def validate_cls(sql_query: str, role: str) -> tuple[bool, str]:
    """
    Validate that a SQL query does not reference forbidden columns.

    Returns (is_allowed, message).
    If the query references a forbidden column, returns (False, error_message).
    """
    forbidden = get_forbidden_columns(role)

    if not forbidden:
        return True, ""

    sql_lower = sql_query.lower()
    for column in forbidden:
        if column.lower() in sql_lower:
            logger.warning(
                "CLS blocked: role='%s' attempted to access forbidden column '%s'.",
                role, column,
            )
            return (
                False,
                f"Access denied: column '{column}' is restricted for role '{role}'.",
            )

    return True, ""


# ---------------------------------------------------------------------------
# CLS filtering (post-execution)
# ---------------------------------------------------------------------------

def filter_columns(rows: list[dict], role: str) -> list[dict]:
    """
    Filter result-set rows to remove columns that the role is not allowed to see.

    If the role has no CLS restrictions, rows are returned unmodified.
    """
    forbidden = get_forbidden_columns(role)

    if not forbidden:
        return rows

    forbidden_lower = {col.lower() for col in forbidden}

    filtered = []
    for row in rows:
        filtered.append({
            key: value
            for key, value in row.items()
            if key.lower() not in forbidden_lower
        })

    if filtered and len(filtered[0]) < len(rows[0]):
        removed = set(rows[0].keys()) - set(filtered[0].keys())
        logger.info("CLS filtered columns: %s for role '%s'.", removed, role)

    return filtered


# ---------------------------------------------------------------------------
# Admin helpers
# ---------------------------------------------------------------------------

def get_all_column_access(role_name: str) -> list[dict]:
    """Get all column access rules for a role (for admin UI)."""
    role_id = _get_role_id(role_name)
    if role_id is None:
        return []

    with engine.connect() as connection:
        result = connection.execute(text("""
            SELECT id, table_name, column_name, is_allowed, created_at
            FROM role_column_access
            WHERE role_id = :role_id
            ORDER BY table_name, column_name
        """), {"role_id": role_id})
        return [dict(row._mapping) for row in result.fetchall()]


def set_column_access(
    role_name: str,
    table_name: str,
    column_name: str,
    is_allowed: bool,
) -> None:
    """Set or update a column access rule for a role."""
    role_id = _get_role_id(role_name)
    if role_id is None:
        raise ValueError(f"Role '{role_name}' not found.")

    with engine.begin() as connection:
        # Upsert: update if exists, insert if not
        existing = connection.execute(text("""
            SELECT id FROM role_column_access
            WHERE role_id = :role_id
              AND table_name = :table_name
              AND column_name = :column_name
        """), {
            "role_id": role_id,
            "table_name": table_name,
            "column_name": column_name,
        }).fetchone()

        if existing:
            connection.execute(text("""
                UPDATE role_column_access
                SET is_allowed = :is_allowed
                WHERE id = :id
            """), {"is_allowed": is_allowed, "id": existing.id})
        else:
            connection.execute(text("""
                INSERT INTO role_column_access (role_id, table_name, column_name, is_allowed)
                VALUES (:role_id, :table_name, :column_name, :is_allowed)
            """), {
                "role_id": role_id,
                "table_name": table_name,
                "column_name": column_name,
                "is_allowed": is_allowed,
            })
