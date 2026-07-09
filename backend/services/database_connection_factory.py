
from sqlalchemy import create_engine
from urllib.parse import quote_plus
from models.connection_config import ConnectionConfig
from services.encryption_service import (
    EncryptionService
)

DATABASE_TYPE_MAP = {
    "mssql": "sqlserver",
    "sqlserver": "sqlserver",

    "postgres": "postgresql",
    "postgresql": "postgresql",

    "mysql": "mysql",
    "sqlite": "sqlite"
}
DEFAULT_DRIVERS = {

    "sqlserver": "ODBC Driver 18 for SQL Server",

    "postgresql": "psycopg2",

    "mysql": "pymysql"

}
class DatabaseConnectionFactory:

    @staticmethod
    def build_connection_string(
        config: ConnectionConfig
    ):

        db_type = config.database_type

        driver = (
            config.driver_name
            or DEFAULT_DRIVERS[db_type]
        )

        # ----------------------------
        # SQL SERVER
        # ----------------------------
        if db_type == "sqlserver":

            authentication_type = (
                config.authentication_type or "SQL"
            ).upper()

            if authentication_type == "WINDOWS":

                return (
                    f"mssql+pyodbc://@"
                    f"{config.host}/"
                    f"{config.database_name}"
                    f"?driver={quote_plus(driver)}"
                    f"&trusted_connection=yes"
                    f"&TrustServerCertificate=yes"
                )

            elif authentication_type == "SQL":

                return (
                    f"mssql+pyodbc://"
                    f"{quote_plus(config.username or '')}:"
                    f"{quote_plus(config.password or '')}@"
                    f"{config.host}/"
                    f"{config.database_name}"
                    f"?driver={quote_plus(driver)}"
                    f"&TrustServerCertificate=yes"
                )

            else:
                raise ValueError(
                    f"Unsupported authentication type: {config.authentication_type}"
                )

        # ----------------------------
        # POSTGRESQL
        # ----------------------------
        elif db_type == "postgresql":

            return (
                f"postgresql+psycopg2://"
                f"{config.username}:"
                f"{config.password}@"
                f"{config.host}:"
                f"{config.port}/"
                f"{config.database_name}"
            )

        # ----------------------------
        # MYSQL
        # ----------------------------
        elif db_type == "mysql":

            return (
                f"mysql+pymysql://"
                f"{config.username}:"
                f"{config.password}@"
                f"{config.host}:"
                f"{config.port}/"
                f"{config.database_name}"
            )

        # ----------------------------
        # SQLITE
        # ----------------------------
        elif db_type == "sqlite":

            return f"sqlite:///{config.database_name}"

        raise ValueError(
            f"Unsupported database type: {db_type}"
        )


    @staticmethod
    def create_engine_for_connection(connection):

        config = DatabaseConnectionFactory.build_config(
            connection
        )

        connection_string = (
            DatabaseConnectionFactory.build_connection_string(
                config
            )
        )

        return create_engine(
            connection_string,
            pool_pre_ping=True
        )

    @staticmethod
    def build_config(connection):

        password = connection.get("password")

        if connection.get("encrypted_password"):
            password = EncryptionService.decrypt(
                connection["encrypted_password"]
            )

        return ConnectionConfig(

            connection_id=connection.get(
                "connection_id",
                ""),

            company_id=connection.get(
                "company_id",
                ""),

            database_type=DATABASE_TYPE_MAP.get(
                connection["database_type"].lower(),
                connection["database_type"].lower()
            ),

            authentication_type=(
                connection.get("authentication_type")
                or "SQL"
            ).upper(),

            host=connection["host"],

            port=connection.get("port"),

            database_name=connection["database_name"],

            username=connection.get("username"),

            password=password,

            driver_name=connection.get("driver_name")
        )