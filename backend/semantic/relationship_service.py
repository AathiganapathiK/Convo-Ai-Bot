from sqlalchemy import text

from database import engine


class SemanticRelationshipService:

    @staticmethod
    def get_relationships(
        connection_id
    ):
        return SemanticRelationshipService.build_relationships(connection_id)


    @staticmethod
    def build_relationships(connection_id):

        query = """
        SELECT
            st_source.table_name AS left_table,
            sc_source.column_name AS left_column,

            st_target.table_name AS right_table,
            sc_target.column_name AS right_column

        FROM schema_relationships sr

        INNER JOIN schema_tables st_source
            ON sr.source_table_id = st_source.table_id

        INNER JOIN schema_columns sc_source
            ON sr.source_column_id = sc_source.column_id

        INNER JOIN schema_tables st_target
            ON sr.target_table_id = st_target.table_id

        INNER JOIN schema_columns sc_target
            ON sr.target_column_id = sc_target.column_id

        WHERE sr.connection_id = :connection_id
        """

        with engine.connect() as conn:

            rows = conn.execute(
                text(query),
                {
                    "connection_id": connection_id
                }
            ).fetchall()


        return rows