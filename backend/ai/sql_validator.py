from ai import schema_loader
import re
import logging
from ai.ast import (
    SQLASTParser,
    SQLASTSecurityValidator,
    SQLASTMetadataExtractor,
    SQLASTSchemaValidator,
)
from ai.repair import RepairEngine
from ai.validation_pipeline import ValidationPipeline

from ai.schema_loader import get_schema_metadata

logger = logging.getLogger(__name__)


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

ast_parser = SQLASTParser()

ast_security_validator = SQLASTSecurityValidator()

ast_metadata_extractor = SQLASTMetadataExtractor()

ast_schema_validator = SQLASTSchemaValidator()

validation_pipeline = ValidationPipeline(
    ast_parser,
    ast_security_validator,
    ast_metadata_extractor,
    ast_schema_validator,
)

repair_engine = RepairEngine(validation_pipeline)

def validate_sql_query(sql_query: str):

    # Remove extra spaces
    sql_query = sql_query.strip()

    sql_query = extract_sql(sql_query)
    # Convert to lowercase for checks
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

    # Step 5: Schema metadata
    schema_metadata = get_schema_metadata()
    if not schema_metadata:
        return False, "Schema metadata is unavailable."

    # Step 6: Run Validation Pipeline
    pipeline_result = validation_pipeline.validate(sql_query, schema_metadata)
    if not pipeline_result.passed:
        # If it failed schema validation, try to repair it
        if pipeline_result.schema_result:
            repair_result = repair_engine.repair_query(pipeline_result, schema_metadata)
            if repair_result.success:
                sql_query = repair_result.repaired_sql
                pipeline_result = repair_result.final_validation
            else:
                return False, str(pipeline_result.schema_result.errors[0])
        else:
            return False, pipeline_result.error

    schema_passed = True
    schema_errors = []

    # Step 9: Shadow Mode
    legacy_valid, legacy_error = validate_schema(sql_query)

    if legacy_valid != schema_passed:
        logger.warning(
            "Schema validator mismatch",
            extra={
                "event": "schema_validation_mismatch",
                "sql": sql_query,
                "legacy": {
                    "passed": legacy_valid,
                    "error": legacy_error,
                },
                "ast": {
                    "passed": schema_passed,
                    "errors": [str(e) for e in schema_errors],
                },
            },
        )

    # Step 10: Return
    return True, sql_query


def extract_tables(sql: str):
    """
    Extract tables from FROM and JOIN clauses.
    """

    pattern = r"(?:FROM|JOIN)\s+([A-Za-z0-9_.]+)"

    return re.findall(pattern, sql, flags=re.IGNORECASE)

def extract_columns(sql: str):
    """
    Extract column names from the SELECT clause.

    A2 Scope:
    - Supports regular columns
    - Supports table aliases (s.Sales)
    - Ignores '*'
    - Ignores SQL functions (handled in A3)
    - Ignores aliases (AS ...)
    """

    match = re.search(
        r"SELECT\s+(.*?)\s+FROM",
        sql,
        flags=re.IGNORECASE | re.DOTALL
    )

    if not match:
        return []

    select_part = match.group(1)

    columns = []

    for item in select_part.split(","):

        item = item.strip()

        if item == "*":
            continue

        # Remove column alias
        item = re.sub(
            r"\s+AS\s+\w+$",
            "",
            item,
            flags=re.IGNORECASE
        )

        # Skip SQL functions (A3)
        if "(" in item or ")" in item:
            continue

        # Remove table alias
        if "." in item:
            item = item.split(".")[-1]

        item = item.strip()

        if item:
            columns.append(item.lower())

    return columns

def extract_alias_map(sql: str):
    """
    Extract table aliases from FROM and JOIN clauses.

    Example:
        FROM Sales S
        JOIN Products P

    Returns:
        {
            "S": "Sales",
            "P": "Products"
        }
    """

    alias_map = {}

    pattern = re.compile(
        r"(?:FROM|JOIN)\s+([A-Za-z0-9_.]+)(?:\s+(?:AS\s+)?([A-Za-z0-9_]+))?",
        re.IGNORECASE
    )

    for match in pattern.finditer(sql):

        table_name = match.group(1)
        alias = match.group(2)

        # Ignore SQL keywords accidentally captured
        if alias and alias.upper() in {
            "ON", "WHERE", "GROUP", "ORDER",
            "INNER", "LEFT", "RIGHT", "FULL",
            "JOIN", "HAVING"
        }:
            alias = None

        if alias:
            alias_map[alias] = table_name
        else:
            # Allow unaliased tables
            alias_map[table_name] = table_name

    return alias_map

def validate_schema(sql_query: str, company_id: str = None):
    """
    Validate that all referenced tables and columns exist
    in the synchronized schema metadata.
    """

    metadata = get_schema_metadata(company_id)

    if not metadata:
        return False, "Schema metadata is unavailable."

    errors = []

    alias_map = extract_alias_map(sql_query)

    # --------------------------------------------------
    # Validate tables
    # --------------------------------------------------

    for table_name in alias_map.values():

        full_table = None

        if table_name in metadata:
            full_table = table_name
        else:
            matches = [
                t
                for t in metadata.keys()
                if t.endswith("." + table_name)
            ]

            if matches:
                full_table = matches[0]

        if full_table is None:
            errors.append(
                f"Table '{table_name}' does not exist."
            )

    # --------------------------------------------------
    # Validate columns
    # --------------------------------------------------

    references = extract_column_references(sql_query)

    for alias, column in references:

        if alias not in alias_map:
            errors.append(
                f"Unknown table alias '{alias}'."
            )
            continue

        table_name = alias_map[alias]

        if table_name not in metadata:

            matches = [
                t
                for t in metadata.keys()
                if t.endswith("." + table_name)
            ]

            if matches:
                table_name = matches[0]
            else:
                continue

        if column.lower() not in metadata[table_name]["columns"]:

            errors.append(
                f"Column '{column}' does not exist in table '{table_name}'."
            )

    if errors:
        return False, errors[0]

    return True, None

def extract_column_references(sql: str):
    """
    Extract all qualified column references from SQL.

    Example:
        S.Sales
        R.Country
        P.ProductKey

    Returns:
        [
            ("S", "Sales"),
            ("R", "Country"),
            ("P", "ProductKey")
        ]
    """

    pattern = re.compile(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b"
    )

    references = []

    for alias, column in pattern.findall(sql):
        references.append((alias, column))

    return references


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