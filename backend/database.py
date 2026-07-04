from sqlalchemy import create_engine
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

DB_TYPE = os.getenv("DB_TYPE", "mssql")  # mssql, mysql, postgres, sqlite
_host = os.getenv("DB_HOST", "localhost")
_port = os.getenv("DB_PORT", "1433")
_name = os.getenv("DB_NAME", "adv_works")
_user = os.getenv("DB_USER", "")
_password = os.getenv("DB_PASSWORD", "")
_driver = os.getenv("DB_DRIVER", "ODBC+Driver+17+for+SQL+Server")


if DB_TYPE == "mssql":
    DATABASE_URL = (
        f"mssql+pyodbc://{quote_plus(_user)}:{quote_plus(_password)}"
        f"@{_host}:{_port}/{_name}"
        f"?driver={quote_plus(_driver)}&TrustServerCertificate=yes"
    )
elif DB_TYPE == "mysql":
    DATABASE_URL = f"mysql+pymysql://{_user}:{_password}@{_host}/{_name}"
elif DB_TYPE == "postgres":
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


"""

To Change Database Anytime:
Just modify .env file:

SQL Server: DB_TYPE=mssql, DB_HOST=your_server
MySQL: DB_TYPE=mysql, DB_USER=root, DB_PASSWORD=pass
PostgreSQL: DB_TYPE=postgres, similar config
SQLite: DB_TYPE=sqlite, DB_NAME=local.db
No code changes needed.

"""