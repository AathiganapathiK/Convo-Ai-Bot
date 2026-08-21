import os
import sys
from sqlalchemy import text

sys.path.append(os.getcwd())
from database import engine

def main():
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE provider_health ADD consecutive_failures INT DEFAULT 0;"))
            print("Successfully added consecutive_failures column.")
        except Exception as e:
            print("Could not add consecutive_failures (might already exist):", e)

if __name__ == "__main__":
    main()
