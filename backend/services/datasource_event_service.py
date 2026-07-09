import uuid
from sqlalchemy import text

from services.db_service import engine


class DatasourceEventService:

    @staticmethod
    def log(
        company_id,
        connection_id,
        lifecycle_type,
        stage,
        status,
        message=None,
        duration_ms=None
    ):

        with engine.begin() as conn:

            conn.execute(
                text("""
                INSERT INTO datasource_lifecycle_events
                (
                    event_id,
                    company_id,
                    connection_id,
                    lifecycle_type,
                    stage,
                    status,
                    message,
                    duration_ms
                )
                VALUES
                (
                    :event_id,
                    :company_id,
                    :connection_id,
                    :lifecycle_type,
                    :stage,
                    :status,
                    :message,
                    :duration_ms
                )
                """),
                {
                    "event_id": str(uuid.uuid4()),
                    "company_id": company_id,
                    "connection_id": connection_id,
                    "lifecycle_type": lifecycle_type,
                    "stage": stage,
                    "status": status,
                    "message": message,
                    "duration_ms": duration_ms
                }
            )