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
        query_all = """
        SELECT
            st.table_name,
            sc.column_name
        FROM schema_tables st
        INNER JOIN schema_columns sc
            ON st.table_id = sc.table_id
        WHERE st.connection_id = :connection_id
        """

        query_rel = """
        SELECT
            st_source.table_name AS left_table,
            sc_source.column_name AS left_column,
            st_target.table_name AS right_table,
            sc_target.column_name AS right_column
        FROM schema_relationships sr
        INNER JOIN schema_tables st_source ON sr.source_table_id = st_source.table_id
        INNER JOIN schema_columns sc_source ON sr.source_column_id = sc_source.column_id
        INNER JOIN schema_tables st_target ON sr.target_table_id = st_target.table_id
        INNER JOIN schema_columns sc_target ON sr.target_column_id = sc_target.column_id
        WHERE sr.connection_id = :connection_id
        """

        with engine.begin() as connection:
            rows = connection.execute(
                text(query_all),
                {"connection_id": connection_id}
            ).fetchall()

            relationships = connection.execute(
                text(query_rel),
                {"connection_id": connection_id}
            ).fetchall()

            all_tables = {}
            for row in rows:
                t = row.table_name
                c = row.column_name
                if t not in all_tables:
                    all_tables[t] = []
                all_tables[t].append(c)

            def get_column_stem_and_suffix(col_name: str):
                col_lower = col_name.lower()
                suffixes = [
                    "key", "id", "code", "no", "num", "seq", "pk", "fk", 
                    "number", "identifier", "reference", "ref"
                ]
                suffixes.sort(key=len, reverse=True)
                for suffix in suffixes:
                    if col_lower.endswith(suffix):
                        stem_part = col_name[:-len(suffix)]
                        stem_part = stem_part.rstrip("_")
                        return stem_part, suffix
                return col_name, None

            def search_table_for_desc_col(T: str, S: str, is_related: bool) -> tuple:
                cols = []
                normalized_T = T
                for t_name, t_cols in all_tables.items():
                    if t_name.lower() == T.lower():
                        normalized_T = t_name
                        cols = t_cols
                        break
                if not cols:
                    return None
                    
                for col in cols:
                    if col.lower() == S.lower():
                        return normalized_T, col
                        
                for col in cols:
                    if col.lower() in (S.lower() + "name", S.lower() + "_name"):
                        return normalized_T, col
                        
                if is_related:
                    t_stem = normalized_T.lower()
                    if t_stem.endswith("s"):
                        t_stem = t_stem[:-1]
                    for col in cols:
                        if col.lower() == normalized_T.lower() or col.lower() == t_stem:
                            return normalized_T, col
                        if col.lower() in (normalized_T.lower() + "name", normalized_T.lower() + "_name", t_stem + "name", t_stem + "_name"):
                            return normalized_T, col
                            
                    for gen in ["name", "description", "title", "desc"]:
                        for col in cols:
                            if col.lower() == gen:
                                return normalized_T, col
                return None

            def find_related_table(T: str, C: str):
                for rel in relationships:
                    left_table, left_column, right_table, right_column = rel[0], rel[1], rel[2], rel[3]
                    if left_table.lower() == T.lower() and left_column.lower() == C.lower():
                        return right_table
                    if right_table.lower() == T.lower() and right_column.lower() == C.lower():
                        return left_table
                return None

            for row in rows:
                t_name = row.table_name
                c_name = row.column_name

                is_key = ColumnDisplayService.is_key_column(c_name)
                visible = not is_key

                display_table = None
                display_column = None

                if is_key:
                    stem, suffix = get_column_stem_and_suffix(c_name)
                    source_matches_stem = (t_name.lower() == stem.lower() or t_name.lower().rstrip("s") == stem.lower())
                    
                    res = search_table_for_desc_col(t_name, stem, is_related=source_matches_stem)
                    if not res:
                        related_t = find_related_table(t_name, c_name)
                        if related_t:
                            res = search_table_for_desc_col(related_t, stem, is_related=True)
                    
                    if res:
                        display_table, display_column = res[0], res[1]

                check_query = """
                SELECT 1 
                FROM column_display_config
                WHERE connection_id = :connection_id
                  AND table_name = :table_name
                  AND column_name = :column_name
                """
                exists = connection.execute(
                    text(check_query),
                    {
                        "connection_id": connection_id,
                        "table_name": t_name,
                        "column_name": c_name
                    }
                ).fetchone()

                if exists:
                    update_query = """
                    UPDATE column_display_config
                    SET display_table = :display_table,
                        display_column = :display_column
                    WHERE connection_id = :connection_id
                      AND table_name = :table_name
                      AND column_name = :column_name
                    """
                    connection.execute(
                        text(update_query),
                        {
                            "connection_id": connection_id,
                            "table_name": t_name,
                            "column_name": c_name,
                            "display_table": display_table,
                            "display_column": display_column
                        }
                    )
                else:
                    insert_query = """
                    INSERT INTO column_display_config
                    (
                        connection_id,
                        table_name,
                        column_name,
                        is_visible,
                        display_table,
                        display_column
                    )
                    VALUES
                    (
                        :connection_id,
                        :table_name,
                        :column_name,
                        :is_visible,
                        :display_table,
                        :display_column
                    )
                    """
                    connection.execute(
                        text(insert_query),
                        {
                            "connection_id": connection_id,
                            "table_name": t_name,
                            "column_name": c_name,
                            "is_visible": visible,
                            "display_table": display_table,
                            "display_column": display_column
                        }
                    )

    @staticmethod
    def load_display_config(connection_id: str):
        query = """
        SELECT
            table_name,
            column_name,
            is_visible,
            display_label,
            display_table,
            display_column
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