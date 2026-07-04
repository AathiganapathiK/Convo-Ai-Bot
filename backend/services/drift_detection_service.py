import uuid

from sqlalchemy import text

from services.db_service import engine
from services.connection_service import ConnectionService
from services.database_connection_factory import DatabaseConnectionFactory

class DriftDetectionService:

    @staticmethod
    def detect_drift(
        company_id: str,
        connection_id: str
    ):

        connection = ConnectionService.get_connection(
            connection_id=connection_id,
            company_id=company_id
        )

        if not connection:
            raise Exception("Connection not found")

        source_engine = (
            DatabaseConnectionFactory
            .create_engine_for_connection(connection)
        )

        with source_engine.connect() as source_conn:

            source_tables = source_conn.execute(
                text("""
                    SELECT
                        TABLE_SCHEMA,
                        TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
                """)
            ).fetchall()

        with engine.connect() as conn:

            metadata_tables = conn.execute(
                text("""
                    SELECT
                        schema_name,
                        table_name
                    FROM schema_tables
                    WHERE connection_id = :connection_id
                """),
                {
                    "connection_id": connection_id
                }
            ).fetchall()

        from services.schema_sync_service import should_sync_table

        source_table_set = {
            f"{row.TABLE_SCHEMA}.{row.TABLE_NAME}"
            for row in source_tables
            if should_sync_table(row.TABLE_NAME)
        }

        metadata_table_set = {
            f"{row.schema_name}.{row.table_name}"
            for row in metadata_tables
        }

        new_tables = (
            source_table_set -
            metadata_table_set
        )

        removed_tables = (
            metadata_table_set -
            source_table_set
        )        

        # ----------------------------------
        # Column Drift Detection
        # ----------------------------------

        with source_engine.connect() as source_conn:

            source_columns = source_conn.execute(
                text("""
                    SELECT
                        TABLE_SCHEMA,
                        TABLE_NAME,
                        COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                """)
            ).fetchall()

        with engine.connect() as conn:

            metadata_columns = conn.execute(
                text("""
                    SELECT
                        st.schema_name,
                        st.table_name,
                        sc.column_name
                    FROM schema_columns sc
                    INNER JOIN schema_tables st
                        ON sc.table_id = st.table_id
                    WHERE st.connection_id = :connection_id
                """),
                {
                    "connection_id": connection_id
                }
            ).fetchall()

        source_column_set = {
            (row.TABLE_SCHEMA, row.TABLE_NAME, row.COLUMN_NAME)
            for row in source_columns
            if should_sync_table(row.TABLE_NAME)
        }

        metadata_column_set = {
            (row.schema_name, row.table_name, row.column_name)
            for row in metadata_columns
        }

        # Filter out columns belonging to new/removed tables to avoid redundancy
        new_columns = {
            (s, t, c) for s, t, c in (source_column_set - metadata_column_set)
            if f"{s}.{t}" not in new_tables
        }

        removed_columns = {
            (s, t, c) for s, t, c in (metadata_column_set - source_column_set)
            if f"{s}.{t}" not in removed_tables
        }


        # ----------------------------------
        # Persist and Resolve Drift Events
        # ----------------------------------

        with engine.begin() as conn:

            # 1. Insert New Tables
            for table_name in new_tables:
                existing = conn.execute(
                    text("""
                        SELECT TOP 1 drift_id
                        FROM schema_drift_events
                        WHERE connection_id = :connection_id
                        AND drift_type = 'NEW_TABLE'
                        AND object_name = :object_name
                        AND is_resolved = 0
                    """),
                    {
                        "connection_id": connection_id,
                        "object_name": table_name
                    }
                ).fetchone()

                if existing:
                    continue

                conn.execute(
                    text("""
                        INSERT INTO schema_drift_events
                        (
                            drift_id,
                            company_id,
                            connection_id,
                            drift_type,
                            object_type,
                            object_name
                        )
                        VALUES
                        (
                            :drift_id,
                            :company_id,
                            :connection_id,
                            'NEW_TABLE',
                            'TABLE',
                            :object_name
                        )
                    """),
                    {
                        "drift_id": str(uuid.uuid4()),
                        "company_id": company_id,
                        "connection_id": connection_id,
                        "object_name": table_name
                    }
                )

            # 2. Insert Removed Tables
            for table_name in removed_tables:
                existing = conn.execute(
                    text("""
                        SELECT TOP 1 drift_id
                        FROM schema_drift_events
                        WHERE connection_id = :connection_id
                        AND drift_type = 'REMOVED_TABLE'
                        AND object_name = :object_name
                        AND is_resolved = 0
                    """),
                    {
                        "connection_id": connection_id,
                        "object_name": table_name
                    }
                ).fetchone()

                if existing:
                    continue

                conn.execute(
                    text("""
                        INSERT INTO schema_drift_events
                        (
                            drift_id,
                            company_id,
                            connection_id,
                            drift_type,
                            object_type,
                            object_name
                        )
                        VALUES
                        (
                            :drift_id,
                            :company_id,
                            :connection_id,
                            'REMOVED_TABLE',
                            'TABLE',
                            :object_name
                        )
                    """),
                    {
                        "drift_id": str(uuid.uuid4()),
                        "company_id": company_id,
                        "connection_id": connection_id,
                        "object_name": table_name
                    }
                )

            # 3. Insert New Columns
            for schema_name, table_name, column_name in new_columns:
                object_name = f"{schema_name}.{table_name}.{column_name}"
                existing = conn.execute(
                    text("""
                        SELECT TOP 1 drift_id
                        FROM schema_drift_events
                        WHERE connection_id = :connection_id
                        AND drift_type = 'NEW_COLUMN'
                        AND object_name = :object_name
                        AND is_resolved = 0
                    """),
                    {
                        "connection_id": connection_id,
                        "object_name": object_name
                    }
                ).fetchone()

                if existing:
                    continue

                conn.execute(
                    text("""
                        INSERT INTO schema_drift_events
                        (
                            drift_id,
                            company_id,
                            connection_id,
                            drift_type,
                            object_type,
                            object_name
                        )
                        VALUES
                        (
                            :drift_id,
                            :company_id,
                            :connection_id,
                            'NEW_COLUMN',
                            'COLUMN',
                            :object_name
                        )
                    """),
                    {
                        "drift_id": str(uuid.uuid4()),
                        "company_id": company_id,
                        "connection_id": connection_id,
                        "object_name": object_name
                    }
                )

            # 4. Insert Removed Columns
            for schema_name, table_name, column_name in removed_columns:
                object_name = f"{schema_name}.{table_name}.{column_name}"
                existing = conn.execute(
                    text("""
                        SELECT TOP 1 drift_id
                        FROM schema_drift_events
                        WHERE connection_id = :connection_id
                        AND drift_type = 'REMOVED_COLUMN'
                        AND object_name = :object_name
                        AND is_resolved = 0
                    """),
                    {
                        "connection_id": connection_id,
                        "object_name": object_name
                    }
                ).fetchone()

                if existing:
                    continue

                conn.execute(
                    text("""
                        INSERT INTO schema_drift_events
                        (
                            drift_id,
                            company_id,
                            connection_id,
                            drift_type,
                            object_type,
                            object_name
                        )
                        VALUES
                        (
                            :drift_id,
                            :company_id,
                            :connection_id,
                            'REMOVED_COLUMN',
                            'COLUMN',
                            :object_name
                        )
                    """),
                    {
                        "drift_id": str(uuid.uuid4()),
                        "company_id": company_id,
                        "connection_id": connection_id,
                        "object_name": object_name
                    }
                )

            # 5. Resolve Table Drifts
            active_table_drifts = list(new_tables.union(removed_tables))
            if active_table_drifts:
                params = {"connection_id": connection_id}
                not_in_clauses = []
                for idx, name in enumerate(active_table_drifts):
                    param_name = f"drift_table_{idx}"
                    params[param_name] = name
                    not_in_clauses.append(f":{param_name}")
                not_in_str = ", ".join(not_in_clauses)
                conn.execute(
                    text(f"""
                        UPDATE schema_drift_events
                        SET
                            is_resolved = 1,
                            resolved_at = GETDATE()
                        WHERE connection_id = :connection_id
                        AND is_resolved = 0
                        AND drift_type IN ('NEW_TABLE', 'REMOVED_TABLE')
                        AND object_name NOT IN ({not_in_str})
                    """),
                    params
                )
            else:
                conn.execute(
                    text("""
                        UPDATE schema_drift_events
                        SET
                            is_resolved = 1,
                            resolved_at = GETDATE()
                        WHERE connection_id = :connection_id
                        AND is_resolved = 0
                        AND drift_type IN ('NEW_TABLE', 'REMOVED_TABLE')
                    """),
                    {"connection_id": connection_id}
                )

            # 6. Resolve Column Drifts
            active_col_drifts = [f"{s}.{t}.{c}" for s, t, c in new_columns.union(removed_columns)]
            if active_col_drifts:
                params = {"connection_id": connection_id}
                not_in_clauses = []
                for idx, name in enumerate(active_col_drifts):
                    param_name = f"drift_col_{idx}"
                    params[param_name] = name
                    not_in_clauses.append(f":{param_name}")
                not_in_str = ", ".join(not_in_clauses)
                conn.execute(
                    text(f"""
                        UPDATE schema_drift_events
                        SET
                            is_resolved = 1,
                            resolved_at = GETDATE()
                        WHERE connection_id = :connection_id
                        AND is_resolved = 0
                        AND drift_type IN ('NEW_COLUMN', 'REMOVED_COLUMN')
                        AND object_name NOT IN ({not_in_str})
                    """),
                    params
                )
            else:
                conn.execute(
                    text("""
                        UPDATE schema_drift_events
                        SET
                            is_resolved = 1,
                            resolved_at = GETDATE()
                        WHERE connection_id = :connection_id
                        AND is_resolved = 0
                        AND drift_type IN ('NEW_COLUMN', 'REMOVED_COLUMN')
                    """),
                    {"connection_id": connection_id}
                )

        return {
            "success": True,
            "new_tables": len(new_tables),
            "removed_tables": len(removed_tables),
            "new_columns": len(new_columns),
            "removed_columns": len(removed_columns)
        }