from services.connection_service import ConnectionService
from services.schema_sync_service import SchemaSyncService
from services.relationship_discovery_service import RelationshipDiscoveryService
from services.drift_detection_service import DriftDetectionService
from semantic.discovery_service import SemanticDiscoveryService
from services.datasource_event_service import DatasourceEventService
from core.error_codes import ErrorCode
from core.exceptions import DatasourceLifecycleException
from sqlalchemy.exc import SQLAlchemyError
from core.api_response import ApiResponse

class DatasourceLifecycleService:

    @staticmethod
    def enable(
        connection_id: str,
        company_id: str
    ):

        lifecycle = {
            "connection_enabled": False,
            "schema_synced": False,
            "relationships_discovered": False,
            "semantic_discovered": False,
            "drift_checked": False
        }

        try:
            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection_id,
                lifecycle_type="ENABLE",
                stage="START",
                status="STARTED",
                message="Datasourc  e enable process started."
            )

            # -----------------------------
            # Enable Connection
            # -----------------------------

            ConnectionService.enable_connection(
                connection_id,
                company_id
            )


            DatasourceEventService.log(
                company_id,
                connection_id,
                "ENABLE",
                "CONNECTION",
                "SUCCESS",
                "Connection enabled."
            )

            lifecycle["connection_enabled"] = True

            connection = (
                ConnectionService
                .get_active_connection(company_id)
            )

            if not connection:
                raise DatasourceLifecycleException(
                    code=ErrorCode.CONNECTION_FAILED,
                    stage="CONNECTION",
                    message="Active connection not found after enabling the datasource.",
                    retryable=True
                )

            # -----------------------------
            # Schema Sync
            # -----------------------------

            schema_result = (
                SchemaSyncService.sync_schema(
                    connection
                )
            )

            DatasourceEventService.log(
                company_id,
                connection_id,
                "ENABLE",
                "SCHEMA_SYNC",
                "SUCCESS",
                "Schema synchronized."
            )

            lifecycle["schema_synced"] = True

            # -----------------------------
            # Relationship Discovery
            # -----------------------------

            relationship_result = (
                RelationshipDiscoveryService
                .discover_relationships(
                    company_id,
                    connection_id
                )
            )

            DatasourceEventService.log(
                company_id,
                connection_id,
                "ENABLE",
                "RELATIONSHIP_DISCOVERY",
                "SUCCESS",
                "Relationships discovered."
            )

            lifecycle[
                "relationships_discovered"
            ] = True

            # -----------------------------
            # Semantic Discovery
            # -----------------------------

            SemanticDiscoveryService.discover(
                connection_id
            )

            DatasourceEventService.log(
                company_id,
                connection_id,
                "ENABLE",
                "SEMANTIC_DISCOVERY",
                "SUCCESS",
                "Semantic layer generated."
            )

            lifecycle[
                "semantic_discovered"
            ] = True

            # -----------------------------
            # Drift Detection
            # -----------------------------

            drift_result = (
                DriftDetectionService.detect_drift(
                    company_id,
                    connection_id
                )
            )
            DatasourceEventService.log(
                company_id,
                connection_id,
                "ENABLE",
                "DRIFT_DETECTION",
                "SUCCESS",
                "Drift detection completed."
            )

            lifecycle[
                "drift_checked"
            ] = True

            DatasourceEventService.log(
                company_id,
                connection_id,
                "ENABLE",
                "COMPLETE",
                "SUCCESS",
                "Datasource enable completed successfully."
            )

            return ApiResponse(

                success=True,

                data={

                    "message": "Datasource enabled successfully.",

                    "lifecycle": lifecycle,

                    "schema": schema_result,

                    "relationships": relationship_result,

                    "drift": drift_result

                }

            )

        except DatasourceLifecycleException:

            ConnectionService.disable_connection(
                connection_id
            )

            raise


        except Exception as ex:

            DatasourceEventService.log(

                company_id=company_id,

                connection_id=connection_id,

                lifecycle_type="ENABLE",

                stage="FAILED",

                status="FAILED",

                message=str(ex)

            )

            ConnectionService.disable_connection(
                connection_id
            )

            raise DatasourceLifecycleException(

                code=ErrorCode.UNKNOWN_ERROR,

                stage="LIFECYCLE",

                message="Datasource enable process failed.",

                details=str(ex),

                retryable=False

            )