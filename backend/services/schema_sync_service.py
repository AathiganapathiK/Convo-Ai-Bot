from services.relationship_discovery_service import RelationshipDiscoveryService
from semantic.discovery_service import SemanticDiscoveryService
import uuid

from sqlalchemy import text

from database import engine

from services.database_connection_factory import (
    DatabaseConnectionFactory
)
from services.column_display_service import ColumnDisplayService

PLATFORM_TABLES = {
    'companies',
    'users',
    'roles',
    'permissions',
    'role_permissions',
    'user_roles',

    'api_keys',
    'base_config',

    'llm_providers',
    'llm_models',
    'llm_fallbacks',
    'provider_health',

    'chat_sessions',
    'chat_messages',

    'schema_tables',
    'schema_columns',
    'schema_relationships',
    'schema_drift_events',

    'database_connections',
    'audit_logs',

    'user_queries',
    'user_usage',
    'user_data_access',
    'role_column_access',

    'semantic_metrics',
    'semantic_dimensions',
    'semantic_relationships',

    'query_examples',

    'prompt_templates',
    'prompt_versions',

    'drifttest'
}

def should_sync_table(
    table_name: str
) -> bool:

    return (
        table_name.lower()
        not in PLATFORM_TABLES
    )


class SchemaSyncService:

    @staticmethod
    def cleanup_duplicate_tables(connection_id):
        """
        Cleans up duplicate tables in schema_tables for the given connection_id.
        Keeps only one 'master' table_id per (connection_id, schema_name, table_name).
        Updates columns and relationships referencing deleted tables to reference the master table.
        """
        with engine.begin() as conn:
            # 1. Find all duplicates
            dup_query = """
            SELECT schema_name, table_name, COUNT(*) as cnt
            FROM schema_tables
            WHERE connection_id = :connection_id
            GROUP BY schema_name, table_name
            HAVING COUNT(*) > 1
            """
            duplicates = conn.execute(text(dup_query), {"connection_id": connection_id}).fetchall()
            
            for dup in duplicates:
                schema_name = dup.schema_name
                table_name = dup.table_name
                
                # Get all table records for this duplicate
                tbls_query = """
                SELECT table_id, last_synced_at
                FROM schema_tables
                WHERE connection_id = :connection_id
                  AND schema_name = :schema_name
                  AND table_name = :table_name
                ORDER BY last_synced_at DESC, table_id ASC
                """
                tbl_rows = conn.execute(text(tbls_query), {
                    "connection_id": connection_id,
                    "schema_name": schema_name,
                    "table_name": table_name
                }).fetchall()
                
                # Select the first one as master, others as duplicates to remove
                master_table_id = tbl_rows[0].table_id
                dups_to_remove = [row.table_id for row in tbl_rows[1:]]
                
                # For each duplicate table to remove:
                for dup_table_id in dups_to_remove:
                    # Get columns for this duplicate table
                    dup_cols = conn.execute(text("""
                        SELECT column_id, column_name
                        FROM schema_columns
                        WHERE table_id = :dup_table_id
                    """), {"dup_table_id": dup_table_id}).fetchall()
                    
                    # Get master columns to map/check duplicates
                    master_cols = conn.execute(text("""
                        SELECT column_id, column_name
                        FROM schema_columns
                        WHERE table_id = :master_table_id
                    """), {"master_table_id": master_table_id}).fetchall()
                    
                    master_col_map = {col.column_name.lower(): col.column_id for col in master_cols}
                    
                    for col in dup_cols:
                        col_name_lower = col.column_name.lower()
                        if col_name_lower in master_col_map:
                            master_column_id = master_col_map[col_name_lower]
                            # Remap relationships from this column to the master column
                            conn.execute(text("""
                                UPDATE schema_relationships
                                SET source_column_id = :master_column_id
                                WHERE source_column_id = :dup_column_id
                            """), {"master_column_id": master_column_id, "dup_column_id": col.column_id})
                            
                            conn.execute(text("""
                                UPDATE schema_relationships
                                SET target_column_id = :master_column_id
                                WHERE target_column_id = :dup_column_id
                            """), {"master_column_id": master_column_id, "dup_column_id": col.column_id})
                            
                            # Delete the duplicate column
                            conn.execute(text("""
                                DELETE FROM schema_columns
                                WHERE column_id = :dup_column_id
                            """), {"dup_column_id": col.column_id})
                        else:
                            # Move the column to the master table
                            conn.execute(text("""
                                UPDATE schema_columns
                                SET table_id = :master_table_id
                                WHERE column_id = :dup_column_id
                            """), {"master_table_id": master_table_id, "dup_column_id": col.column_id})
                            # Add to master map for subsequent checks
                            master_col_map[col_name_lower] = col.column_id
                    
                    # Remap relationships referencing the duplicate table_id
                    conn.execute(text("""
                        UPDATE schema_relationships
                        SET source_table_id = :master_table_id
                        WHERE source_table_id = :dup_table_id
                    """), {"master_table_id": master_table_id, "dup_table_id": dup_table_id})
                    
                    conn.execute(text("""
                        UPDATE schema_relationships
                        SET target_table_id = :master_table_id
                        WHERE target_table_id = :dup_table_id
                    """), {"master_table_id": master_table_id, "dup_table_id": dup_table_id})
                    
                    # Delete duplicate table row
                    conn.execute(text("""
                        DELETE FROM schema_tables
                        WHERE table_id = :dup_table_id
                    """), {"dup_table_id": dup_table_id})

            # Deduplicate relationships for the connection
            rel_dup_query = """
            SELECT source_table_id, source_column_id, target_table_id, target_column_id, COUNT(*) as cnt
            FROM schema_relationships
            WHERE connection_id = :connection_id
            GROUP BY source_table_id, source_column_id, target_table_id, target_column_id
            HAVING COUNT(*) > 1
            """
            rel_duplicates = conn.execute(text(rel_dup_query), {"connection_id": connection_id}).fetchall()
            for r_dup in rel_duplicates:
                r_rows = conn.execute(text("""
                    SELECT relationship_id
                    FROM schema_relationships
                    WHERE connection_id = :connection_id
                      AND source_table_id = :source_table_id
                      AND source_column_id = :source_column_id
                      AND target_table_id = :target_table_id
                      AND target_column_id = :target_column_id
                """), {
                    "connection_id": connection_id,
                    "source_table_id": r_dup.source_table_id,
                    "source_column_id": r_dup.source_column_id,
                    "target_table_id": r_dup.target_table_id,
                    "target_column_id": r_dup.target_column_id
                }).fetchall()
                
                rels_to_delete = [row.relationship_id for row in r_rows[1:]]
                for rel_id in rels_to_delete:
                    conn.execute(text("""
                        DELETE FROM schema_relationships
                        WHERE relationship_id = :rel_id
                    """), {"rel_id": rel_id})

    @staticmethod
    def sync_schema(
        connection_record,
        db_connection = None
    ):
        company_id = connection_record["company_id"]
        connection_id = connection_record["connection_id"]

        # 1. Clean up duplicate tables
        SchemaSyncService.cleanup_duplicate_tables(connection_id)

        source_engine = DatabaseConnectionFactory.create_engine_for_connection(connection_record)

        # 2. Discover source tables
        with source_engine.connect() as conn:
            source_tables = conn.execute(
                text("""
                SELECT
                    TABLE_SCHEMA,
                    TABLE_NAME,
                    TABLE_TYPE
                FROM
                    INFORMATION_SCHEMA.TABLES
                ORDER BY
                    TABLE_SCHEMA,
                    TABLE_NAME
                """)
            ).fetchall()
            
            source_tables = [
                table
                for table in source_tables
                if should_sync_table(table.TABLE_NAME)
            ]

        # 3. Get existing tables in metadata
        with engine.connect() as conn:
            existing_rows = conn.execute(
                text("""
                SELECT table_id, schema_name, table_name, table_type
                FROM schema_tables
                WHERE connection_id = :connection_id
                """),
                {"connection_id": connection_id}
            ).fetchall()
            
        existing_tables = {
            (row.schema_name.lower(), row.table_name.lower()): row
            for row in existing_rows
        }

        inserted_tables = 0
        updated_tables = 0
        skipped_tables = 0
        removed_tables = 0

        discovered_keys = set()

        for table in source_tables:
            schema_name = table.TABLE_SCHEMA
            table_name = table.TABLE_NAME
            table_type = table.TABLE_TYPE
            key = (schema_name.lower(), table_name.lower())
            discovered_keys.add(key)

            if key in existing_tables:
                existing_row = existing_tables[key]
                table_id = existing_row.table_id
                
                # Check if attributes changed
                if existing_row.table_type != table_type:
                    with engine.begin() as conn:
                        conn.execute(
                            text("""
                            UPDATE schema_tables
                            SET table_type = :table_type, last_synced_at = GETDATE()
                            WHERE table_id = :table_id
                            """),
                            {"table_type": table_type, "table_id": table_id}
                        )
                    updated_tables += 1
                else:
                    with engine.begin() as conn:
                        conn.execute(
                            text("""
                            UPDATE schema_tables
                            SET last_synced_at = GETDATE()
                            WHERE table_id = :table_id
                            """),
                            {"table_id": table_id}
                        )
                    skipped_tables += 1
            else:
                table_id = str(uuid.uuid4())
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                        INSERT INTO schema_tables
                        (
                            table_id,
                            company_id,
                            connection_id,
                            schema_name,
                            table_name,
                            table_type,
                            last_synced_at
                        )
                        VALUES
                        (
                            :table_id,
                            :company_id,
                            :connection_id,
                            :schema_name,
                            :table_name,
                            :table_type,
                            GETDATE()
                        )
                        """),
                        {
                            "table_id": table_id,
                            "company_id": company_id,
                            "connection_id": connection_id,
                            "schema_name": schema_name,
                            "table_name": table_name,
                            "table_type": table_type
                        }
                    )
                inserted_tables += 1

            # Discover & synchronize columns for this table
            with source_engine.connect() as conn:
                columns = conn.execute(
                    text("""
                    SELECT
                        COLUMN_NAME,
                        DATA_TYPE,
                        CHARACTER_MAXIMUM_LENGTH,
                        NUMERIC_PRECISION,
                        NUMERIC_SCALE,
                        IS_NULLABLE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = :schema_name
                      AND TABLE_NAME = :table_name
                    """),
                    {
                        "schema_name": schema_name,
                        "table_name": table_name
                    }
                ).fetchall()

            # Get existing columns in metadata for this table
            with engine.connect() as conn:
                existing_cols = conn.execute(
                    text("""
                    SELECT column_id, column_name, data_type, max_length, numeric_precision, numeric_scale, is_nullable
                    FROM schema_columns
                    WHERE table_id = :table_id
                    """),
                    {"table_id": table_id}
                ).fetchall()
                
            existing_columns = {
                row.column_name.lower(): row
                for row in existing_cols
            }

            discovered_col_names = set()

            for column in columns:
                col_name = column.COLUMN_NAME
                col_name_lower = col_name.lower()
                discovered_col_names.add(col_name_lower)

                data_type = column.DATA_TYPE
                max_length = column.CHARACTER_MAXIMUM_LENGTH
                numeric_precision = column.NUMERIC_PRECISION
                numeric_scale = column.NUMERIC_SCALE
                is_nullable = (str(column.IS_NULLABLE).upper() == "YES")

                if col_name_lower in existing_columns:
                    existing_col = existing_columns[col_name_lower]
                    column_id = existing_col.column_id

                    # Check for updates
                    if (existing_col.data_type != data_type or
                        existing_col.max_length != max_length or
                        existing_col.numeric_precision != numeric_precision or
                        existing_col.numeric_scale != numeric_scale or
                        bool(existing_col.is_nullable) != is_nullable):
                        
                        with engine.begin() as conn:
                            conn.execute(
                                text("""
                                UPDATE schema_columns
                                SET data_type = :data_type,
                                    max_length = :max_length,
                                    numeric_precision = :numeric_precision,
                                    numeric_scale = :numeric_scale,
                                    is_nullable = :is_nullable
                                WHERE column_id = :column_id
                                """),
                                {
                                    "column_id": column_id,
                                    "data_type": data_type,
                                    "max_length": max_length,
                                    "numeric_precision": numeric_precision,
                                    "numeric_scale": numeric_scale,
                                    "is_nullable": is_nullable
                                }
                            )
                else:
                    column_id = str(uuid.uuid4())
                    with engine.begin() as conn:
                        conn.execute(
                            text("""
                            INSERT INTO schema_columns
                            (
                                column_id,
                                company_id,
                                table_id,
                                column_name,
                                data_type,
                                max_length,
                                numeric_precision,
                                numeric_scale,
                                is_nullable
                            )
                            VALUES
                            (
                                :column_id,
                                :company_id,
                                :table_id,
                                :column_name,
                                :data_type,
                                :max_length,
                                :numeric_precision,
                                :numeric_scale,
                                :is_nullable
                            )
                            """),
                            {
                                "column_id": column_id,
                                "company_id": company_id,
                                "table_id": table_id,
                                "column_name": col_name,
                                "data_type": data_type,
                                "max_length": max_length,
                                "numeric_precision": numeric_precision,
                                "numeric_scale": numeric_scale,
                                "is_nullable": is_nullable
                            }
                        )

            # Clean up columns that no longer exist in the source table
            removed_cols = [
                row.column_id
                for row in existing_cols
                if row.column_name.lower() not in discovered_col_names
            ]
            if removed_cols:
                with engine.begin() as conn:
                    for col_id in removed_cols:
                        conn.execute(
                            text("""
                            DELETE FROM schema_relationships
                            WHERE source_column_id = :col_id OR target_column_id = :col_id
                            """),
                            {"col_id": col_id}
                        )
                        conn.execute(
                            text("""
                            DELETE FROM schema_columns
                            WHERE column_id = :col_id
                            """),
                            {"col_id": col_id}
                        )

        # 4. Clean up tables that no longer exist in source database
        for key, existing_row in existing_tables.items():
            if key not in discovered_keys:
                table_id = existing_row.table_id
                with engine.begin() as conn:
                    # Delete relationships
                    conn.execute(
                        text("""
                        DELETE FROM schema_relationships
                        WHERE source_table_id = :table_id OR target_table_id = :table_id
                        """),
                        {"table_id": table_id}
                    )
                    # Delete columns
                    conn.execute(
                        text("""
                        DELETE FROM schema_columns
                        WHERE table_id = :table_id
                        """),
                        {"table_id": table_id}
                    )
                    # Delete table
                    conn.execute(
                        text("""
                        DELETE FROM schema_tables
                        WHERE table_id = :table_id
                        """),
                        {"table_id": table_id}
                    )
                removed_tables += 1

        # 5. Stats Logging
        print(f"[SCHEMA SYNC] Connection {connection_id} synchronized: "
              f"{inserted_tables} inserted, {updated_tables} updated, "
              f"{skipped_tables} skipped, {removed_tables} removed.")

        # 6. Auto-populate column display config
        ColumnDisplayService.auto_populate_display_config(connection_id)

        return {
            "success": True,
            "message": f"Schema sync completed. {inserted_tables} tables inserted, {updated_tables} updated, {skipped_tables} skipped, {removed_tables} removed.",
            "stats": {
                "inserted": inserted_tables,
                "updated": updated_tables,
                "skipped": skipped_tables,
                "removed": removed_tables
            }
        }

    