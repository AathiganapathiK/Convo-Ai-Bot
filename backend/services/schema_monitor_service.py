import time
import threading

from services.connection_service import ConnectionService
from services.schema_sync_service import SchemaSyncService
from services.relationship_discovery_service import (
    RelationshipDiscoveryService
)
from services.drift_detection_service import (
    DriftDetectionService
)

from database import engine
from sqlalchemy import text


class SchemaMonitorService:

    @staticmethod
    def monitor():

        while True:

            try:

                with engine.connect() as conn:

                    connections = conn.execute(
                        text("""
                        SELECT *
                        FROM database_connections
                        WHERE is_active = 1
                        """)
                    ).fetchall()

                for row in connections:

                    connection = dict(
                        row._mapping
                    )

                    drift = (
                        DriftDetectionService
                        .detect_drift(
                            company_id=connection["company_id"],
                            connection_id=connection["connection_id"]
                        )
                    )

                    drift_found = (
                        drift["new_tables"] > 0
                        or drift["removed_tables"] > 0
                        or drift["new_columns"] > 0
                        or drift["removed_columns"] > 0
                    )

                    if drift_found:

                        print(
                            f"Schema drift detected: "
                            f"{connection['connection_name']}"
                        )

                        SchemaSyncService.sync_schema(
                            connection
                        )

                        RelationshipDiscoveryService.discover_relationships(
                            company_id=connection["company_id"],
                            connection_id=connection["connection_id"]
                        )

            except Exception as e:

                print(
                    f"Schema monitor error: {e}"
                )

            time.sleep(300)

    @staticmethod
    def start():

        thread = threading.Thread(
            target=SchemaMonitorService.monitor,
            daemon=True
        )

        thread.start()