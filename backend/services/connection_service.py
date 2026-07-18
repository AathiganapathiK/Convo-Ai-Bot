from sqlalchemy import text

from database import engine
from services.encryption_service import EncryptionService
from services.datasource_event_service import DatasourceEventService

class ConnectionService:

    @staticmethod
    def get_connections(
        company_id: str = None
    ):

        query = """
        SELECT
            connection_id,
            connection_name,
            database_type,
            host,
            port,
            database_name,
            username,
            is_active,
            last_tested_at,
            last_sync_at,
            created_at
        FROM database_connections
        ORDER BY connection_name
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query)
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]

    @staticmethod
    def create_connection(
        company_id: str,
        request
    ):

        encrypted_password = None

        if request.password:

            encrypted_password = (
                EncryptionService.encrypt(
                    request.password
                )
            )

        query = """
        INSERT INTO database_connections
        (
            company_id,
            connection_name,
            database_type,
            host,
            port,
            database_name,
            username,
            encrypted_password,
            connection_string,
            is_active
        )
        OUTPUT INSERTED.connection_id
        VALUES
        (
            :company_id,
            :connection_name,
            :database_type,
            :host,
            :port,
            :database_name,
            :username,
            :encrypted_password,
            :connection_string,
            1
        )
        """

        with engine.begin() as connection:

            result = connection.execute(
                text(query),
                {
                    "company_id": company_id,
                    "connection_name": request.connection_name,
                    "database_type": request.database_type,
                    "host": request.host,
                    "port": request.port,
                    "database_name": request.database_name,
                    "username": request.username,
                    "encrypted_password": encrypted_password,
                    "connection_string": request.connection_string
                }
            )

            connection_id = str(result.scalar())
                
        DatasourceEventService.log(
                company_id=company_id,
                connection_id=connection_id,
                lifecycle_type="REGISTER",
                stage="CREATE_CONNECTION",
                status="SUCCESS",
                message="Datasource connection registered successfully."
            )

        return connection_id


    @staticmethod
    def disable_connection(
        connection_id: str,
        company_id: str = None
    ):

        query = """
        UPDATE database_connections
        SET
            is_active = 0,
            updated_at = GETDATE()
        WHERE
            connection_id = :connection_id
        """

        with engine.begin() as connection:

            connection.execute(
                text(query),
                {
                    "connection_id": connection_id
                }
            )
        return True

    @staticmethod
    def get_connection(
        connection_id: str,
        company_id: str = None
    ):

        query = """
        SELECT *
        FROM database_connections
        WHERE
            connection_id = :connection_id
        """

        with engine.connect() as conn:

            result = conn.execute(
                text(query),
                {
                    "connection_id": connection_id
                }
            ).fetchone()

        if not result:
            return None

        return dict(
            result._mapping
        )

    @staticmethod
    def get_active_connection(
        company_id: str = None
    ):
        return ConnectionService.get_active_connection_global()

    @staticmethod
    def enable_connection(
        connection_id: str,
        company_id: str = None
    ):
        # Disable all other connections globally first
        disable_others_query = """
        UPDATE database_connections
        SET is_active = 0,
            updated_at = GETDATE()
        WHERE connection_id != :connection_id
        """
        # Enable the selected connection
        enable_query = """
        UPDATE database_connections
        SET is_active = 1,
            updated_at = GETDATE()
        WHERE connection_id = :connection_id
        """
        with engine.begin() as conn:
            conn.execute(
                text(disable_others_query),
                {
                    "connection_id": connection_id
                }
            )
            conn.execute(
                text(enable_query),
                {
                    "connection_id": connection_id
                }
            )
        return True


    @staticmethod
    def get_active_connection_global():

        query = """
        SELECT TOP 1 *
        FROM database_connections
        WHERE is_active = 1
        """

        with engine.connect() as conn:
            result = conn.execute(
                text(query)
            ).fetchone()

        if not result:
            return None

        return dict(result._mapping)