from database import engine as platform_engine

from services.connection_service import (
    ConnectionService
)

from services.database_connection_factory import (
    DatabaseConnectionFactory
)


class ConnectionManager:

    @staticmethod
    def platform():
        return platform_engine

    @staticmethod
    def source(company_id=None, connection=None):
        if not connection:
            connection = (
                ConnectionService.get_active_connection_global()
            )

        if not connection:
            raise Exception(
                "No active database connection"
            )

        return (
            DatabaseConnectionFactory
            .create_engine_for_connection(
                connection
            )
        )