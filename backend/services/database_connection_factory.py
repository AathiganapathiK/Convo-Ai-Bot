from sqlalchemy import create_engine
from urllib.parse import quote_plus

from services.encryption_service import (
    EncryptionService
)


class DatabaseConnectionFactory:

    @staticmethod
    def build_connection_string(
        connection
    ):

        db_type = (
            connection["database_type"]
            .lower()
        )

        password = None

        if connection.get(
            "encrypted_password"
        ):
            password = (
                EncryptionService.decrypt(
                    connection[
                        "encrypted_password"
                    ]
                )
            )

        if db_type == "sqlserver":

            if connection.get(
                "use_windows_auth",
                True
            ):

                quoted_user = quote_plus(connection.get("username") or "")
                quoted_password = quote_plus(password or "")
                return (
                    f"mssql+pyodbc://{quoted_user}:{quoted_password}@"
                    f"{connection['host']}/"
                    f"{connection['database_name']}"
                    f"?driver=ODBC+Driver+17+for+SQL+Server"
                    f"&TrustServerCertificate=yes"
                )

            quoted_user = quote_plus(connection.get("username") or "")
            quoted_password = quote_plus(password or "")
            return (
                f"mssql+pyodbc://"
                f"{quoted_user}:"
                f"{quoted_password}@"
                f"{connection['host']}/"
                f"{connection['database_name']}"
                f"?driver=ODBC+Driver+17+for+SQL+Server"
                f"&TrustServerCertificate=yes"
            )

        elif db_type == "postgresql":

            return (
                f"postgresql+psycopg2://"
                f"{connection['username']}:"
                f"{password}@"
                f"{connection['host']}:"
                f"{connection['port']}/"
                f"{connection['database_name']}"
            )

        elif db_type == "mysql":

            return (
                f"mysql+pymysql://"
                f"{connection['username']}:"
                f"{password}@"
                f"{connection['host']}:"
                f"{connection['port']}/"
                f"{connection['database_name']}"
            )

        raise Exception(
            f"Unsupported database type: {db_type}"
        )

    @staticmethod
    def create_engine_for_connection(
        connection
    ):

        connection_string = (
            DatabaseConnectionFactory
            .build_connection_string(
                connection
            )
        )

        return create_engine(
            connection_string,
            pool_pre_ping=True
        )