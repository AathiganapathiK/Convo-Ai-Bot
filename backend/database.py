from sqlalchemy import create_engine
import core.config
import os

from urllib.parse import quote_plus


DB_TYPE = ( 
    os.getenv("DB_TYPE", "sqlserver")
    .strip()
    .lower()
)

DATABASE_TYPE_MAP = {
    
    "mssql": "sqlserver",
    "sqlserver": "sqlserver",

    "postgres": "postgresql",
    "postgresql": "postgresql",

    "mysql": "mysql",
    "sqlite": "sqlite"
}

DB_TYPE = DATABASE_TYPE_MAP.get(DB_TYPE, DB_TYPE)

_host = os.getenv("DB_HOST", "localhost")
_port = os.getenv("DB_PORT", "")
_name = os.getenv("DB_NAME", "adv_works")
_user = os.getenv("DB_USER", "")
_password = os.getenv("DB_PASSWORD", "")
_driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")


if DB_TYPE == "sqlserver":

    connection_string = (
        f"DRIVER={{{_driver}}};"
        f"SERVER={_host};"
        f"DATABASE={_name};"
        f"UID={_user};"
        f"PWD={_password};"
        f"TrustServerCertificate=yes;"
    )

    DATABASE_URL = (
        "mssql+pyodbc:///?odbc_connect="
        + quote_plus(connection_string)
    )
    
elif DB_TYPE == "mysql":
    DATABASE_URL = f"mysql+pymysql://{_user}:{_password}@{_host}/{_name}"
elif DB_TYPE == "postgresql":
    DATABASE_URL = f"postgresql+psycopg2://{_user}:{_password}@{_host}/{_name}"
elif DB_TYPE == "sqlite":
    DATABASE_URL = f"sqlite:///{_name}.db"
else:
    raise ValueError(f"Unsupported DB_TYPE: {DB_TYPE}")


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

print("DATABASE_url", DATABASE_URL)

"""

To Change Database Anytime:
Just modify .env file:

SQL Server: DB_TYPE=mssql, DB_HOST=your_server
MySQL: DB_TYPE=mysql, DB_USER=root, DB_PASSWORD=pass
PostgreSQL: DB_TYPE=postgres, similar config
SQLite: DB_TYPE=sqlite, DB_NAME=local.db
No code changes needed.

"""