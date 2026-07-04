FORBIDDEN_COLUMNS = {
    "ANALYST": ["profit", "cost"]
}

def validate_cls(sql_query: str, role: str):
    """
    Column-Level Security validator.
    Blocks access to restricted columns based on the user's role.
    Role comparison is case-insensitive.
    """
    forbidden = FORBIDDEN_COLUMNS.get(role.upper(), [])
    sql_lower = sql_query.lower()
    for column in forbidden:
        if column.lower() in sql_lower:
            return (
                False,
                f"Access denied: column '{column}' is restricted for role '{role}'."
            )
    return True, ""