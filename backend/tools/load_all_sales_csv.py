import pandas as pd
from sqlalchemy import create_engine
import urllib
import os

SERVER_NAME = "localhost"
DATABASE_NAME = "adv_works"

connection_string = urllib.parse.quote_plus(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={SERVER_NAME};"
    f"DATABASE={DATABASE_NAME};"
    f"Trusted_Connection=yes;"
)

engine = create_engine(
    f"mssql+pyodbc:///?odbc_connect={connection_string}"
)

files = {
    "Sales": os.getenv("SALES_CSV_PATH", r"C:\Users\aathi\Downloads\Sales\Sales.csv")
}

for table_name, file_name in files.items():

    print(f"\nLoading {table_name}...")

    df = pd.read_fwf(file_name)

    print(df.head())

    df.to_sql(
        table_name,
        engine,
        if_exists="replace",
        index=False
    )

    print(f"{table_name} loaded successfully")

print("\nAll tables imported successfully.")
