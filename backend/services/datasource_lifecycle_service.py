from admin import connection_management
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

    @staticmethod
    def disable(
        connection_id: str,
        company_id: str
    ):
        DatasourceEventService.log(
            company_id=company_id,
            connection_id=connection_id,
            lifecycle_type="DISABLE",
            stage="START",
            status="STARTED",
            message="Datasource disable process started."
        )

        ConnectionService.disable_connection(
            connection_id=connection_id,
            company_id=company_id
        )

        DatasourceEventService.log(
            company_id=company_id,
            connection_id=connection_id,
            lifecycle_type="DISABLE",
            stage="CONNECTION",
            status="SUCCESS",
            message="Datasource disabled successfully."
        )

        DatasourceEventService.log(
            company_id=company_id,
            connection_id=connection_id,
            lifecycle_type="DISABLE",
            stage="COMPLETE",
            status="SUCCESS",
            message="Datasource disable completed successfully."
        )

        return {
            "success": True,
            "message": "Connection disabled."
        }

    @staticmethod
    def sync(
        connection_id: str,
        company_id: str
    ):
        connection = ConnectionService.get_active_connection(company_id)

        if not connection:
            return {
                "success": False,
                "message": "No active database connection found"
            }

        DatasourceEventService.log(
            company_id=company_id,
            connection_id=connection["connection_id"],
            lifecycle_type="SYNC",
            stage="START",
            status="STARTED",
            message="Schema synchronization started."
        )

        try:
            result = SchemaSyncService.sync_schema(connection)

            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection["connection_id"],
                lifecycle_type="SYNC",
                stage="SCHEMA_SYNC",
                status="SUCCESS",
                message="Schema synchronization completed successfully."
            )

            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection["connection_id"],
                lifecycle_type="SYNC",
                stage="COMPLETE",
                status="SUCCESS",
                message="Schema sync lifecycle completed successfully."
            )

            return result
        except Exception as e:
            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection["connection_id"],
                lifecycle_type="SYNC",
                stage="SCHEMA_SYNC",
                status="FAILED",
                message=str(e)
            )

            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection["connection_id"],
                lifecycle_type="SYNC",
                stage="COMPLETE",
                status="FAILED",
                message="Schema sync lifecycle failed."
            )
            raise

    @staticmethod
    def discover_relationships(
        connection_id: str,
        company_id: str
    ):
        connection = ConnectionService.get_active_connection(company_id)

        if not connection:
            return {
                "success": False,
                "message": "No active database connection found"
            }

        DatasourceEventService.log(
            company_id=company_id,
            connection_id=connection["connection_id"],
            lifecycle_type="RELATIONSHIP_DISCOVERY",
            stage="START",
            status="STARTED",
            message="Relationship discovery started."
        )

        try:
            result = RelationshipDiscoveryService.discover_relationships(
                company_id=company_id,
                connection_id=connection["connection_id"]
            )

            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection["connection_id"],
                lifecycle_type="RELATIONSHIP_DISCOVERY",
                stage="DISCOVERY",
                status="SUCCESS",
                message="Relationship discovery completed successfully."
            )

            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection["connection_id"],
                lifecycle_type="RELATIONSHIP_DISCOVERY",
                stage="COMPLETE",
                status="SUCCESS",
                message="Relationship discovery lifecycle completed successfully."
            )

            return result
        except Exception as e:
            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection["connection_id"],
                lifecycle_type="RELATIONSHIP_DISCOVERY",
                stage="DISCOVERY",
                status="FAILED",
                message=str(e)
            )

            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection["connection_id"],
                lifecycle_type="RELATIONSHIP_DISCOVERY",
                stage="COMPLETE",
                status="FAILED",
                message="Relationship discovery lifecycle failed."
            )
            raise

    @staticmethod
    def detect_drift(
        connection_id: str,
        company_id: str
    ):
        connection = ConnectionService.get_active_connection(company_id)

        if not connection:
            return {
                "success": False,
                "message": "No active database connection found"
            }

        DatasourceEventService.log(
            company_id=company_id,
            connection_id=connection["connection_id"],
            lifecycle_type="DRIFT_DETECTION",
            stage="START",
            status="STARTED",
            message="Drift detection started."
        )

        try:
            result = DriftDetectionService.detect_drift(
                company_id=company_id,
                connection_id=connection["connection_id"]
            )

            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection["connection_id"],
                lifecycle_type="DRIFT_DETECTION",
                stage="ANALYSIS",
                status="SUCCESS",
                message="Drift detection completed successfully."
            )

            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection["connection_id"],
                lifecycle_type="DRIFT_DETECTION",
                stage="COMPLETE",
                status="SUCCESS",
                message="Drift detection lifecycle completed successfully."
            )

            return result
        except Exception as e:
            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection["connection_id"],
                lifecycle_type="DRIFT_DETECTION",
                stage="ANALYSIS",
                status="FAILED",
                message=str(e)
            )

            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection["connection_id"],
                lifecycle_type="DRIFT_DETECTION",
                stage="COMPLETE",
                status="FAILED",
                message="Drift detection lifecycle failed."
            )
            raise