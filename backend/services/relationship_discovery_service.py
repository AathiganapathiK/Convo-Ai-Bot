import uuid

from sqlalchemy import text

from services.db_service import engine
from services.connection_service import ConnectionService
from services.database_connection_factory import DatabaseConnectionFactory


class RelationshipDiscoveryService:

    @staticmethod
    def discover_relationships(
        company_id: str,
        connection_id: str
    ):

        # Get connection details
        connection = ConnectionService.get_connection(
            connection_id=connection_id,
            company_id=company_id
        )

        if not connection:
            raise Exception("Connection not found")

        # Create source database engine
        source_engine = (
            DatabaseConnectionFactory
            .create_engine_for_connection(
                connection
            )
        )

        # Remove old discovered relationships
        with engine.begin() as conn:

            conn.execute(
                text("""
                    DELETE FROM schema_relationships
                    WHERE connection_id = :connection_id
                """),
                {
                    "connection_id": connection_id
                }
            )

            conn.execute(
                text("""
                    UPDATE schema_columns
                    SET is_foreign_key = 0,
                        is_primary_key = 0
                    WHERE table_id IN
                    (
                        SELECT table_id
                        FROM schema_tables
                        WHERE connection_id = :connection_id
                    )
                """),
                {
                    "connection_id": connection_id
                }
            )

        relationships_found = 0

        # Read foreign keys from source database
        with source_engine.connect() as source_conn:

            foreign_keys = source_conn.execute(
                text("""
                    SELECT
                        fk.name AS foreign_key_name,

                        OBJECT_SCHEMA_NAME(
                            fkc.parent_object_id
                        ) AS source_schema,

                        OBJECT_NAME(
                            fkc.parent_object_id
                        ) AS source_table,

                        pc.name AS source_column,

                        OBJECT_SCHEMA_NAME(
                            fkc.referenced_object_id
                        ) AS target_schema,

                        OBJECT_NAME(
                            fkc.referenced_object_id
                        ) AS target_table,

                        rc.name AS target_column

                    FROM sys.foreign_key_columns fkc

                    INNER JOIN sys.foreign_keys fk
                        ON fk.object_id =
                           fkc.constraint_object_id

                    INNER JOIN sys.columns pc
                        ON pc.object_id =
                           fkc.parent_object_id
                       AND pc.column_id =
                           fkc.parent_column_id

                    INNER JOIN sys.columns rc
                        ON rc.object_id =
                           fkc.referenced_object_id
                       AND rc.column_id =
                           fkc.referenced_column_id
                """)
            ).fetchall()


            print("=" * 50)
            print("FOREIGN KEYS FOUND:", len(foreign_keys))

            for fk in foreign_keys:

                print(fk.source_table,
                    "->",
                    fk.target_table
                )

            print("=" * 50)

        # Process each relationship
        with engine.begin() as conn:

            for fk in foreign_keys:

                # Source table
                source_table = conn.execute(
                    text("""
                        SELECT table_id
                        FROM schema_tables
                        WHERE connection_id = :connection_id
                        AND schema_name = :schema_name
                        AND table_name = :table_name
                    """),
                    {
                        "connection_id": connection_id,
                        "schema_name": fk.source_schema,
                        "table_name": fk.source_table
                    }
                ).fetchone()

                # Target table
                target_table = conn.execute(
                    text("""
                        SELECT table_id
                        FROM schema_tables
                        WHERE connection_id = :connection_id
                        AND schema_name = :schema_name
                        AND table_name = :table_name
                    """),
                    {
                        "connection_id": connection_id,
                        "schema_name": fk.target_schema,
                        "table_name": fk.target_table
                    }
                ).fetchone()

                if not source_table or not target_table:
                    continue

                # Source column
                source_column = conn.execute(
                    text("""
                        SELECT column_id
                        FROM schema_columns
                        WHERE table_id = :table_id
                        AND column_name = :column_name
                    """),
                    {
                        "table_id": source_table.table_id,
                        "column_name": fk.source_column
                    }
                ).fetchone()

                # Target column
                target_column = conn.execute(
                    text("""
                        SELECT column_id
                        FROM schema_columns
                        WHERE table_id = :table_id
                        AND column_name = :column_name
                    """),
                    {
                        "table_id": target_table.table_id,
                        "column_name": fk.target_column
                    }
                ).fetchone()

                if not source_column or not target_column:
                    continue

                # Insert relationship
                conn.execute(
                    text("""
                        INSERT INTO schema_relationships
                        (
                            relationship_id,
                            company_id,
                            connection_id,
                            source_table_id,
                            source_column_id,
                            target_table_id,
                            target_column_id,
                            relationship_type,
                            confidence_score,
                            is_confirmed,
                            discovered_by
                        )
                        VALUES
                        (
                            :relationship_id,
                            :company_id,
                            :connection_id,
                            :source_table_id,
                            :source_column_id,
                            :target_table_id,
                            :target_column_id,
                            :relationship_type,
                            :confidence_score,
                            :is_confirmed,
                            :discovered_by
                        )
                    """),
                    {
                        "relationship_id": str(uuid.uuid4()),
                        "company_id": company_id,
                        "connection_id": connection_id,
                        "source_table_id": source_table.table_id,
                        "source_column_id": source_column.column_id,
                        "target_table_id": target_table.table_id,
                        "target_column_id": target_column.column_id,
                        "relationship_type": "FOREIGN_KEY",
                        "confidence_score": 1.0,
                        "is_confirmed": True,
                        "discovered_by": "SYSTEM"
                    }
                )

                # Mark FK column
                conn.execute(
                    text("""
                        UPDATE schema_columns
                        SET is_foreign_key = 1
                        WHERE column_id = :column_id
                    """),
                    {
                        "column_id": source_column.column_id
                    }
                )

                relationships_found += 1

                # --------------------------------------------------
        # Discover Primary Keys
        # --------------------------------------------------

        with source_engine.connect() as source_conn:

            primary_keys = source_conn.execute(
                text("""
                    SELECT
                        KU.TABLE_SCHEMA,
                        KU.TABLE_NAME,
                        KU.COLUMN_NAME

                    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS TC

                    INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE KU
                        ON TC.CONSTRAINT_NAME = KU.CONSTRAINT_NAME

                    WHERE TC.CONSTRAINT_TYPE = 'PRIMARY KEY'
                """)
            ).fetchall()

        with engine.begin() as conn:

            for pk in primary_keys:

                table_row = conn.execute(
                    text("""
                        SELECT table_id
                        FROM schema_tables
                        WHERE connection_id = :connection_id
                        AND schema_name = :schema_name
                        AND table_name = :table_name
                    """),
                    {
                        "connection_id": connection_id,
                        "schema_name": pk.TABLE_SCHEMA,
                        "table_name": pk.TABLE_NAME
                    }
                ).fetchone()

                if not table_row:
                    continue

                conn.execute(
                    text("""
                        UPDATE schema_columns
                        SET is_primary_key = 1
                        WHERE table_id = :table_id
                        AND column_name = :column_name
                    """),
                    {
                        "table_id": table_row.table_id,
                        "column_name": pk.COLUMN_NAME
                    }
                )

        return {
            "success": True,
            "relationships_found": relationships_found,
            "primary_keys_discovered": len(primary_keys)
        }