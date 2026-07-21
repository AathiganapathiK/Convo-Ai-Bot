from sqlalchemy.engine import row
from sqlalchemy import text

from database import engine


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
        limit=5
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
            ).fetchall()

        if not rows:
            return []

        matched_examples = []
        rel_tables_lower = {t.lower() for t in relevant_tables} if relevant_tables else set()

        for row in rows:
            ex_q = row[0]
            ex_sql = row[1].lower() if row[1] else ""
            
            if not rel_tables_lower:
                return []

            if any(t.lower() in ex_sql for t in rel_tables_lower):
                matched_examples.append(
                    {
                        "question": ex_q,
                        "sql_query": row[1]
                    }
                )

            if len(matched_examples) >= limit:
                break

        return matched_examples

        