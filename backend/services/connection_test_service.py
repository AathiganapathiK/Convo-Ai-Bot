from sqlalchemy import text

from database import engine

from services.database_connection_factory import (
    DatabaseConnectionFactory
)


class ConnectionTestService:

    @staticmethod
    def test_payload(
        payload
    ):

        engine_obj = (
            DatabaseConnectionFactory
            .create_engine_for_connection(
                payload
            )
        )

        with engine_obj.connect() as conn:

            conn.execute(
                text("SELECT 1")
            )

        return {
            "success": True,
            "message":
                "Connection successful"
        }