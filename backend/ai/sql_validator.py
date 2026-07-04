import re

# Block dangerous SQL operations
BLOCKED_KEYWORDS = [
    "delete",
    "drop",
    "update",
    "insert",
    "alter",
    "truncate",
    "create",
    "exec",
    "execute",
    "merge"
]

def validate_sql_query(sql_query: str ):

    # Remove extra spaces
    sql_query = sql_query.strip()

    sql_query = extract_sql(sql_query)
    # Convert to lowercase for ch
    # ecks
    sql_query = re.sub(
        r"<think>.*?</think>",
        "",
        sql_query,
        flags=re.DOTALL | re.IGNORECASE
    ).strip()
    lower_query = sql_query.lower()

    # Rule 1: Only SELECT queries allowed
    if not lower_query.startswith("select"):
        return False, "Only SELECT queries are allowed"

    # Rule 2: Block dangerous keywords
    for keyword in BLOCKED_KEYWORDS:

        # Regex word boundary match
        pattern = rf"\b{keyword}\b"

        if re.search(pattern, lower_query):
            return False, f"{keyword.upper()} operations are not allowed"

    # Rule 3: Prevent multiple SQL statements
    if ";" in sql_query[:-1]:
        return False, "Multiple SQL statements are not allowed"

    # Rule 4: Block SQL comments
    blocked_comment_patterns = [
        "--",
        "/*",
        "*/"
    ]

    for pattern in blocked_comment_patterns:
        if pattern in lower_query:
            return False, "SQL comments are not allowed"

    return True, sql_query


def enforce_row_limit(sql_query: str):
    """Inject TOP 100 if no TOP clause exists. Case-insensitive."""
    if re.search(r"\btop\b", sql_query, re.IGNORECASE):
        return sql_query

    # Handle SELECT DISTINCT
    if re.match(r"^\s*select\s+distinct\b", sql_query, re.IGNORECASE):
        return re.sub(
            r"(?i)^(\s*select\s+distinct)",
            r"\1 TOP 100",
            sql_query,
            count=1
        )

    return re.sub(
        r"(?i)^(\s*select)",
        r"\1 TOP 100",
        sql_query,
        count=1
    )

def extract_sql(text):
    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    match = re.search(
        r"(SELECT\s+.*)",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    return match.group(1).strip() if match else ""