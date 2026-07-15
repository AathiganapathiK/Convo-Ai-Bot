from sqlalchemy import text

from database import engine


class RelevantSchemaService:

    @staticmethod
    def get_schema(
        connection_id,
        tables
    ):

        if not tables:
            return ""

        placeholders = ",".join(
            f":table{i}"
            for i in range(len(tables))
        )

        query = f"""
        SELECT
            st.table_name,
            sc.column_name,
            sc.data_type
        FROM schema_columns sc
        JOIN schema_tables st
            ON sc.table_id = st.table_id
        WHERE st.connection_id = :connection_id
        AND st.table_name IN ({placeholders})
        ORDER BY
            st.table_name,
            sc.column_name
        """

        params = {
            "connection_id": connection_id
        }

        for i, table in enumerate(tables):
            params[f"table{i}"] = table

        with engine.connect() as conn:
            rows = conn.execute(
                text(query),
                params
            ).fetchall()

        schema = ""

        current_table = None

        for row in rows:

            if current_table != row[0]:

                current_table = row[0]

                schema += f"\nTable: {current_table}\n"

            schema += (
                f"  - {row[1]}"
                f" ({row[2]})\n"
            )

        return schema