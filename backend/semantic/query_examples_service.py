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
        limit=5
    ):

        with engine.connect() as conn:

            rows = conn.execute(
                text("""
                SELECT TOP (:limit)
                    question,
                    sql_query
                FROM query_examples
                WHERE connection_id =
                    :connection_id
                ORDER BY created_at DESC
                """),
                {
                    "connection_id": connection_id,
                    "limit": limit
                }
            ).fetchall()

        return [
            {
                "question": row[0],
                "sql_query": row[1]
            }
            for row in rows
        ]

        