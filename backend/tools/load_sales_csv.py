import os
import pandas as pd
from sqlalchemy import create_engine
import urllib
from dotenv import load_dotenv

load_dotenv()

connection_string = urllib.parse.quote_plus(
    f"DRIVER={os.getenv('DB_DRIVER')};"
    f"SERVER={os.getenv('DB_HOST')};"
    f"DATABASE={os.getenv('DB_NAME')};"
    f"Trusted_Connection=yes;"
)

engine = create_engine(
    f"mssql+pyodbc:///?odbc_connect={connection_string}"
)

sales_file = os.getenv("SALES_CSV_PATH", r"C:\Users\aathi\Downloads\Sales\Sales.csv")

print("Loading Sales.csv...")

# Read Tab Delimited File
df = pd.read_csv(
    sales_file,
    sep="\t",
    engine="python"
)

print("\nColumns:")
print(df.columns.tolist())

print("\nSample Data:")
print(df.head())

# Load into SQL Server
df.to_sql(
    "Sales",
    engine,
    if_exists="replace",
    index=False
)

print("\nSales table loaded successfully.")
