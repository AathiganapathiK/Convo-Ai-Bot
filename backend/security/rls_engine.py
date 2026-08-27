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
import sqlglot
from sqlglot import parse_one, exp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Access type → SQL column candidate mapping
# ---------------------------------------------------------------------------

ACCESS_TYPE_COLUMNS = {
    "REGION":       ["SalesTerritoryKey", "region", "region_code", "territory"],
    "DIVISION":     ["division", "division_code"],
    "PRODUCT":      ["product", "product_name", "product_category", "product_code", "category"],
    "CHANNEL":      ["channel", "sales_channel", "channel_code", "segment"],
    "SALESPERSON":  ["EmployeeKey", "salesperson_id"]
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
        access_type = row.access_type.upper()
        if access_type not in rules:
            rules[access_type] = []
        rules[access_type].append(row.access_value)

    return rules


# ---------------------------------------------------------------------------
# AST-Based RLS Filter Injection (sqlglot)
# ---------------------------------------------------------------------------

def apply_rls(
    sql_query: str,
    user: dict,
) -> tuple[str, dict]:
    """
    Inject AST-aware RLS filters into a SQL query based on the user's effective data matrix.
    Uses sqlglot AST parsing for safe alias, JOIN, subquery, and CTE handling.

    Parameters:
        sql_query:  The generated SQL query string.
        user:       The authenticated user dict from get_current_user().

    Returns:
        (modified_sql, rls_metadata) where rls_metadata describes what was applied.
    """
    role = user.get("role", "")
    employee_id = user.get("employee_id", "")
    company_id = user.get("company_id", "")

    metadata = {"rls_applied": True, "filters": []}

    # SUPER_ADMIN bypasses RLS
    if role.upper() == "SUPER_ADMIN" or user.get("is_super_admin"):
        return sql_query, {"rls_applied": False, "reason": "super_admin_bypass"}

    # Fetch effective user data matrix (role scopes + explicit user overrides)
    from services.access_control_service import AccessControlService
    effective_matrix = AccessControlService.get_effective_user_matrix(user)
    effective_scopes = effective_matrix.get("data_scope", {})

    # Determine dimensions to filter
    active_filters = {}
    for access_type, candidates in ACCESS_TYPE_COLUMNS.items():
        values = effective_scopes.get(access_type, [])
        if not values and access_type in ("REGION", "SALESPERSON"):
            direct_rules = get_user_access_rules(employee_id)
            values = direct_rules.get(access_type, [])

        if values:
            active_filters[access_type] = {
                "candidates": candidates,
                "values": values
            }

    if not active_filters:
        return sql_query, {"rls_applied": False, "reason": "no_filters"}

    # AST Processing via sqlglot
    try:
        ast = parse_one(sql_query, dialect="tsql")
        
        # Build map of candidate column names to table aliases
        column_to_table = {}
        tables = list(ast.find_all(exp.Table))
        default_table_alias = tables[0].alias_or_name if tables else None

        # Inspect all columns in AST
        all_ast_columns = list(ast.find_all(exp.Column))
        for col_node in all_ast_columns:
            c_name = col_node.name.lower()
            t_alias = col_node.table or default_table_alias
            column_to_table[c_name] = t_alias

        ast_modified = False

        for access_type, info in active_filters.items():
            candidates = info["candidates"]
            values = info["values"]

            # Match candidate column in query AST or fallback to first candidate
            target_col = None
            target_alias = default_table_alias

            for col in candidates:
                if col.lower() in column_to_table:
                    target_col = col
                    target_alias = column_to_table[col.lower()]
                    break

            if not target_col:
                target_col = candidates[0]

            # Construct AST exp.In expression
            in_clause = exp.In(
                this=exp.column(target_col, table=target_alias),
                expressions=[exp.Literal.string(str(v)) for v in values]
            )

            ast = ast.where(in_clause, append=True)
            ast_modified = True

            metadata["filters"].append({
                "access_type": access_type,
                "column": target_col,
                "table_alias": target_alias,
                "values": values,
            })

        if ast_modified:
            modified_sql = ast.sql(dialect="tsql")
            logger.info(
                "AST RLS applied for user='%s', company='%s': %s filters applied",
                employee_id,
                company_id,
                len(metadata["filters"]),
            )
            return modified_sql, metadata

    except Exception as err:
        logger.warning("AST RLS parsing failed for user='%s': %s. Falling back to safe string injection.", employee_id, err)

    # Fail-Safe Fallback: String-based injection with sanitized parameters
    string_filters = []
    sql_lower = sql_query.lower()
    for access_type, info in active_filters.items():
        candidates = info["candidates"]
        values = info["values"]
        matched_col = None
        for col in candidates:
            if col.lower() in sql_lower:
                matched_col = col
                break
        if not matched_col:
            matched_col = candidates[0]

        clean_values = [str(v).replace("'", "''") for v in values]
        quoted_values = ", ".join(f"'{v}'" for v in clean_values)
        string_filters.append(f"{matched_col} IN ({quoted_values})")

        metadata["filters"].append({
            "access_type": access_type,
            "column": matched_col,
            "values": values,
        })

    combined_filter = " AND ".join(string_filters)
    modified_sql = _inject_where_clause(sql_query, combined_filter)
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
