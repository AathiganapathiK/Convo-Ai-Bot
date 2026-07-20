from services.connection_service import ConnectionService
from sqlalchemy.engine import result
from sqlalchemy import text
from database import engine


class DatasourceCleanupService:

    @staticmethod
    def cleanup(
        connection,
        connection_id: str,
        company_id: str
    ):

            summary = {
                "column_display": 0,
                "semantic_dimensions": 0,
                "semantic_metrics": 0,
                "semantic_relationships": 0,
                "schema_relationships": 0,
                "schema_drift_events": 0,
                "schema_columns": 0,
                "schema_tables": 0
            }

            summary["column_display"] = (
                DatasourceCleanupService._delete_column_display(
                    connection,
                    connection_id,
                    company_id
                )
            )

            print(f"[DELETE] Column Display removed: {summary['column_display']}")

            summary.update(
                DatasourceCleanupService._delete_semantic_layer(
                    connection,
                    connection_id,
                    company_id
                )
            )

            summary.update(
                DatasourceCleanupService._delete_schema_metadata(
                    connection,
                    connection_id,
                    company_id
                )
            )


            print(
                "[DELETE] Schema Metadata:",
                {
                    "relationships": summary["schema_relationships"],
                    "columns": summary["schema_columns"],
                    "tables": summary["schema_tables"]
                }
            )

            summary["schema_drift_events"] = (
                DatasourceCleanupService._delete_drift_history(
                    connection,
                    connection_id,
                    company_id
                )
            )

            # summary["lifecycle_events"] = (
            #     DatasourceCleanupService._delete_lifecycle_history(
            #         connection,
            #         connection_id,
            #         company_id
            #     )
            # )
            # print(
            #     f"[DELETE] Lifecycle Events removed: "
            #     f"{summary.get('lifecycle_events', 0)}"
            # )
            return summary

    @staticmethod
    def _delete_column_display(
        connection,
        connection_id,
        company_id
    ):
        result = connection.execute(
            text("""
                DELETE FROM column_display_config
                WHERE connection_id = :connection_id
            """),
            {
                "connection_id": connection_id
            }
        )

        return result.rowcount

    @staticmethod
    def _delete_semantic_layer(
        connection,
        connection_id,
        company_id
    ):
        return {
            "semantic_dimensions": 0,
            "semantic_metrics": 0,
            "semantic_relationships": 0
        }

    @staticmethod
    def _delete_schema_metadata(
        connection,
        connection_id,
        company_id
    ):
        summary = {
            "schema_relationships": 0,
            "schema_columns": 0,
            "schema_tables": 0
        }

        #
        # Delete relationships
        #
        result = connection.execute(
            text("""
                DELETE FROM schema_relationships
                WHERE connection_id = :connection_id
            """),
            {
                "connection_id": connection_id
            }
        )

        summary["schema_relationships"] = result.rowcount

        #
        # Delete columns
        #
        result = connection.execute(
            text("""
                DELETE FROM schema_columns
                WHERE table_id IN (
                    SELECT table_id
                    FROM schema_tables
                    WHERE connection_id = :connection_id
                )
            """),
            {
                "connection_id": connection_id
            }
        )

        summary["schema_columns"] = result.rowcount

        #
        # Delete tables
        #
        result = connection.execute(
            text("""
                DELETE FROM schema_tables
                WHERE connection_id = :connection_id
            """),
            {
                "connection_id": connection_id
            }
        )

        summary["schema_tables"] = result.rowcount

        return summary

    @staticmethod
    def _delete_drift_history(
        connection,
        connection_id,
        company_id
    ):
        return 0

    # @staticmethod
    # def _delete_lifecycle_history(
    #     connection,
    #     connection_id,
    #     company_id
    # ):
    #     result = connection.execute(
    #         text("""
    #             DELETE FROM datasource_lifecycle_events
    #             WHERE connection_id = :connection_id
    #         """),
    #         {
    #             "connection_id": connection_id
    #         }
    #     )

    #     return result.rowcount


    @staticmethod
    def get_delete_summary(
        connection_id: str,
        company_id: str
    ):
        summary = {
            "column_display": 0,
            "schema_tables": 0,
            "schema_columns": 0,
            "schema_relationships": 0,
            "schema_drift_events": 0,
            "semantic_dimensions": 0,
            "semantic_metrics": 0,
            "semantic_relationships": 0,
            "lifecycle_events": 0
        }

        with engine.connect() as connection:

            summary["schema_tables"] = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM schema_tables
                    WHERE connection_id = :connection_id
                """),
                {"connection_id": connection_id}
            ).scalar()

            summary["schema_columns"] = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM schema_columns
                    WHERE table_id IN (
                        SELECT table_id
                        FROM schema_tables
                        WHERE connection_id = :connection_id
                    )
                """),
                {"connection_id": connection_id}
            ).scalar()

            summary["schema_relationships"] = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM schema_relationships
                    WHERE connection_id = :connection_id
                """),
                {
                    "connection_id": connection_id
                }
            ).scalar()
            summary["column_display"] = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM column_display_config
                    WHERE connection_id = :connection_id
                """),
                {
                    "connection_id": connection_id
                }
            ).scalar()

            summary["semantic_dimensions"] = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM semantic_dimensions
                    WHERE connection_id = :connection_id
                """),
                {
                    "connection_id": connection_id
                }
            ).scalar()

            summary["semantic_metrics"] = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM semantic_metrics
                    WHERE connection_id = :connection_id
                """),
                {
                    "connection_id": connection_id
                }
            ).scalar()

            summary["semantic_relationships"] = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM semantic_relationships
                    WHERE connection_id = :connection_id
                """),
                {
                    "connection_id": connection_id
                }
            ).scalar()

            summary["lifecycle_events"] = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM datasource_lifecycle_events
                    WHERE connection_id = :connection_id
                """),
                {
                    "connection_id": connection_id
                }
            ).scalar()

        return summary

