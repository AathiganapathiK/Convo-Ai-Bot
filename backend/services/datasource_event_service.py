from fastapi import status
import uuid
import logging
from sqlalchemy import text

from services.db_service import engine
logger = logging.getLogger(__name__)

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

        if not company_id:
            raise ValueError("company_id is required")

        if not connection_id:
            raise ValueError("connection_id is required")

        if not lifecycle_type:
            raise ValueError("lifecycle_type is required")

        if not stage:
            raise ValueError("stage is required")

        if not status:
            raise ValueError("status is required")

        event_id = str(uuid.uuid4())
        try:

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
                        "event_id": event_id,
                        "company_id": company_id,
                        "connection_id": connection_id,
                        "lifecycle_type": lifecycle_type,
                        "stage": stage,
                        "status": status,
                        "message": message,
                        "duration_ms": duration_ms
                    }
                )

        except Exception:

            logger.exception(
                "Failed to write datasource lifecycle event."
            )

            raise
        
        return event_id