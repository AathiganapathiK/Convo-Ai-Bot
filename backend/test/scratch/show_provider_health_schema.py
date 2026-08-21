import os
import sys
from sqlalchemy import text, inspect

# Add backend directory to path
sys.path.append(os.getcwd())

from database import engine

def show_schema():
    print("Inspecting provider_health table...")
    inspector = inspect(engine)
    if inspector.has_table("provider_health"):
        columns = inspector.get_columns("provider_health")
        for col in columns:
            print(f"Column: {col['name']} | Type: {col['type']}")
    else:
        print("Table provider_health does not exist.")

if __name__ == "__main__":
    show_schema()
