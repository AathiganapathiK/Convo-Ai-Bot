import traceback
from admin import connection_management
from sqlalchemy import text

from database import engine

from services.database_connection_factory import (
    DatabaseConnectionFactory
)
from services.connection_service import ConnectionService
from services.datasource_event_service import DatasourceEventService

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

    @staticmethod
    def test_connection(
        connection_id: str,
        company_id: str
    ):

        connection = ConnectionService.get_connection(
            connection_id,
            company_id
        )
        
        if not connection:
            return {
                "success": False,
                "message": "Connection not found."
            }
        DatasourceEventService.log(
            company_id=company_id,
            connection_id=connection_id,
            lifecycle_type="TEST",
            stage="START",
            status="STARTED",
            message="Datasource connection test started."
        )


        print("\n" + "=" * 80)
        print("TEST CONNECTION")
        print("Connection ID :", connection["connection_id"])
        print("Connection Name :", connection["connection_name"])
        print("Database :", connection["database_name"])
        print("Host :", connection["host"])
        print("Port :", connection["port"])
        print("Database Type :", connection["database_type"])
        print("Username :", connection["username"])
        print("=" * 80)


        try:
            engine_obj = (
                DatabaseConnectionFactory
                .create_engine_for_connection(connection)
            )

            with engine_obj.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection_id,
                lifecycle_type="TEST",
                stage="CONNECTION",
                status="SUCCESS",
                message="Database connection test succeeded."
            )

            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection_id,
                lifecycle_type="TEST",
                stage="COMPLETE",
                status="SUCCESS",
                message="Datasource connection test completed successfully."
            )

            return {
                "success": True,
                "message": "Connection successful."
            }

        except Exception as ex:
            print("=" * 80)
            print("DATABASE CONNECTION TEST FAILED")
            traceback.print_exc()
            print("Exception Type:", type(ex).__name__)
            print("Exception Repr:", repr(ex))
            print("Exception Str :", str(ex))
            print("=" * 80)

            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection_id,
                lifecycle_type="TEST",
                stage="CONNECTION",
                status="FAILED",
                message=str(ex)
            )

            DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection_id,
                lifecycle_type="TEST",
                stage="COMPLETE",
                status="FAILED",
                message="Datasource connection test failed."
            )

            
            raise   