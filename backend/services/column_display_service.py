from sqlalchemy import text

from database import engine


class ColumnDisplayService:

    KEY_SUFFIXES = (
        "key",
        "id",
        "code",
        "no",
        "num",
        "seq",
        "pk",
        "fk"
    )

    @staticmethod
    def is_key_column(column_name: str) -> bool:

        column = column_name.lower()

        return any(
            column.endswith(suffix)
            for suffix in ColumnDisplayService.KEY_SUFFIXES
        )

    @staticmethod
    def auto_populate_display_config(connection_id: str):

        query = """
        SELECT
            st.table_name,
            sc.column_name
        FROM schema_tables st
        INNER JOIN schema_columns sc
            ON st.table_id = sc.table_id
        WHERE st.connection_id = :connection_id
        """

        with engine.begin() as connection:

            rows = connection.execute(
                text(query),
                {
                    "connection_id": connection_id
                }
            ).fetchall()

            for row in rows:

                visible = (
                    not ColumnDisplayService.is_key_column(
                        row.column_name
                    )
                )

                connection.execute(
                    text("""
                    IF NOT EXISTS
                    (
                        SELECT 1
                        FROM column_display_config
                        WHERE
                            connection_id = :connection_id
                            AND table_name = :table_name
                            AND column_name = :column_name
                    )
                    INSERT INTO column_display_config
                    (
                        connection_id,
                        table_name,
                        column_name,
                        is_visible
                    )
                    VALUES
                    (
                        :connection_id,
                        :table_name,
                        :column_name,
                        :is_visible
                    )
                    """),
                    {
                        "connection_id": connection_id,
                        "table_name": row.table_name,
                        "column_name": row.column_name,
                        "is_visible": visible
                    }
                )

    @staticmethod
    def load_display_config(connection_id: str):

        query = """
        SELECT
            table_name,
            column_name,
            is_visible,
            display_label
        FROM column_display_config
        WHERE connection_id = :connection_id
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "connection_id": connection_id
                }
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]


    @staticmethod
    def apply_display_config(
        rows: list,
        connection_id: str
    ):

        if not rows:
            return rows

        config = (
            ColumnDisplayService
            .load_display_config(connection_id)
        )

        hidden_columns = {
            item["column_name"].lower()
            for item in config
            if not item["is_visible"]
        }

        if not hidden_columns:
            return rows

        filtered_rows = []

        for row in rows:

            filtered_rows.append(
                {
                    key: value
                    for key, value in row.items()
                    if key.lower() not in hidden_columns
                }
            )

        return filtered_rows