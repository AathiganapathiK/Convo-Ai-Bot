from sqlalchemy.engine import row
from sqlalchemy import text
import re
from sqlglot import parse_one, exp

from database import engine


def is_date_or_period_column(col_name: str, val: str) -> bool:
    col_lower = col_name.lower()
    val_str = str(val).strip()
    
    # Check column name keywords
    for keyword in ['date', 'month', 'year', 'quarter', 'week', 'time']:
        if keyword in col_lower:
            return True
            
    # Check value patterns (like YYYY-MM-DD or YYYY-MM)
    if re.match(r'^\d{4}-\d{2}-\d{2}', val_str):
        return True
    if re.match(r'^\d{4}-\d{2}', val_str):
        return True
    return False


def extract_business_value_filters(sql: str) -> list[dict]:
    if not sql:
        return []
    try:
        ast = parse_one(sql, dialect="tsql")
    except Exception:
        return []

    filters = []
    for expression in ast.find_all(exp.Expression):
        # EQ: col = 'value'
        if isinstance(expression, exp.EQ):
            left = expression.left
            right = expression.right
            
            col = None
            lit = None
            if isinstance(left, exp.Column) and isinstance(right, exp.Literal):
                col = left
                lit = right
            elif isinstance(right, exp.Column) and isinstance(left, exp.Literal):
                col = right
                lit = left
                
            if col and lit and lit.is_string:
                col_name = col.name
                val_str = lit.this
                if not is_date_or_period_column(col_name, val_str):
                    filters.append({
                        "column": col_name.lower().strip(),
                        "value": val_str.lower().strip()
                    })
        # IN: col IN ('val1', 'val2')
        elif isinstance(expression, exp.In):
            col = expression.this
            if isinstance(col, exp.Column):
                col_name = col.name
                for val in expression.expressions:
                    if isinstance(val, exp.Literal) and val.is_string:
                        val_str = val.this
                        if not is_date_or_period_column(col_name, val_str):
                            filters.append({
                                "column": col_name.lower().strip(),
                                "value": val_str.lower().strip()
                            })
    return filters


class QueryExamplesService:

    @staticmethod
    def store(
        question,
        sql_query,
        connection_id
    ):

        with engine.begin() as conn:

            conn.execute(
                text("""
                INSERT INTO query_examples
                (
                    connection_id,
                    question,
                    sql_query
                )
                VALUES
                (
                    :connection_id,
                    :question,
                    :sql_query
                )
                """),
                {
                    "connection_id": connection_id,
                    "question": question,
                    "sql_query": sql_query
                }
            )
            
    @staticmethod
    def retrieve(
        connection_id,
        relevant_tables=None,
        limit=5,
        value_matches=None,
        metric_objects=None
    ):

        with engine.connect() as conn:

            rows = conn.execute(
                text("""
                SELECT TOP (50)
                    question,
                    sql_query
                FROM query_examples
                WHERE connection_id = :connection_id
                ORDER BY created_at DESC
                """),
                {
                    "connection_id": connection_id
                }
            )
            raw_rows = rows.fetchall()

        if not raw_rows:
            return []

        # Convert rows from CursorResult to list of tuples/mappings
        row_tuples = []
        for r in raw_rows:
            if hasattr(r, "_mapping"):
                row_tuples.append(dict(r._mapping))
            elif isinstance(r, (list, tuple)) and len(r) >= 2:
                row_tuples.append({
                    "question": r[0],
                    "sql_query": r[1]
                })
            else:
                row_tuples.append(dict(r))

        current_resolved_values = []
        for f in (value_matches or []):
            if isinstance(f, dict):
                col = f.get("column_name") or f.get("dimension") or f.get("business_name") or f.get("dimension_name")
                val = f.get("value")
                if col is not None and val is not None:
                    current_resolved_values.append({
                        "column": str(col).lower().strip(),
                        "value": str(val).lower().strip()
                    })

        matched_examples = []
        rel_tables_lower = {t.lower() for t in relevant_tables} if relevant_tables else set()

        for r_dict in row_tuples:
            ex_q = r_dict.get("question")
            ex_sql_raw = r_dict.get("sql_query")
            ex_sql = ex_sql_raw.lower() if ex_sql_raw else ""
            
            if not rel_tables_lower:
                return []

            # Check if this example is compatible with the current required value filters
            is_compatible = True
            if value_matches:
                for f in value_matches:
                    if isinstance(f, dict):
                        col = f.get("column_name") or f.get("dimension") or f.get("business_name") or f.get("dimension_name")
                        val = f.get("value")
                        if col is not None and val is not None:
                            col_lower = str(col).lower().strip()
                            # Exclude if required column filter is missing from example SQL
                            if col_lower not in ex_sql:
                                is_compatible = False
                                break

            # Verify that any business value filters present in the example SQL are also
            # requested / resolved by the current query.
            if is_compatible:
                example_filters = extract_business_value_filters(ex_sql_raw)
                for ex_f in example_filters:
                    # Check if this exact filter (column + value) is present in the current resolved values
                    matched = False
                    for cur in current_resolved_values:
                        if cur["column"] == ex_f["column"] and cur["value"] == ex_f["value"]:
                            matched = True
                            break
                    if not matched:
                        is_compatible = False
                        
                        # Diagnostic output as requested
                        print("\nEXCLUDED_EXAMPLE")
                        print("Reason:")
                        print("EXTRA_VALUE_FILTER")
                        print(f"\nExample filter:\n{ex_f['column']} = '{ex_f['value']}'")
                        print("\nCurrent resolved values:")
                        if current_resolved_values:
                            print("\n".join(f"{c['column']} = '{c['value']}'" for c in current_resolved_values))
                        else:
                            print("NONE")
                        print("================\n")
                        break

            # Check if this example is compatible with the current resolved metrics
            if is_compatible and metric_objects:
                current_cols = {str(m.get("column_name")).lower() for m in metric_objects if m.get("column_name")}
                known_period_cols = {'cy', 'py', 'pytd', 'ppy', 'pppy', 'cyq', 'pyq', 'ppyq', 'ppppy', 'ppppyq'}
                current_period_cols = current_cols.intersection(known_period_cols)
                
                if current_period_cols:
                    conflicting_period_cols = known_period_cols - current_period_cols
                    for conf_col in conflicting_period_cols:
                        pattern = rf"\b{re.escape(conf_col)}\b"
                        if re.search(pattern, ex_sql):
                            has_current = False
                            for cur_col in current_period_cols:
                                cur_pattern = rf"\b{re.escape(cur_col)}\b"
                                if re.search(cur_pattern, ex_sql):
                                    has_current = True
                                    break
                            if not has_current:
                                is_compatible = False
                                break

            if not is_compatible:
                continue

            if any(t.lower() in ex_sql for t in rel_tables_lower):
                matched_examples.append(
                    {
                        "question": ex_q,
                        "sql_query": ex_sql_raw
                    }
                )

            if len(matched_examples) >= limit:
                break

        return matched_examples


        