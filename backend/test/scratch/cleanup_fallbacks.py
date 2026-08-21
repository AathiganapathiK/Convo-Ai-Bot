import os
import sys
from sqlalchemy import text

# Add backend directory to path
sys.path.append(os.getcwd())

from database import engine

def cleanup():
    print("Starting fallback duplicates cleanup...")
    with engine.begin() as conn:
        # Fetch all fallbacks with their model details
        rows = conn.execute(text("""
            SELECT f.fallback_id, f.company_id, f.purpose, f.priority_order, m.model_name, m.provider_id
            FROM llm_fallbacks f
            INNER JOIN llm_models m ON f.model_id = m.model_id
            WHERE f.is_active = 1
            ORDER BY f.company_id, f.purpose, f.priority_order
        """)).fetchall()

        seen = set()
        duplicates_to_delete = []

        for r in rows:
            # Group unique by company, purpose, provider, and model name
            key = (r.company_id, r.purpose, r.provider_id, r.model_name)
            if key in seen:
                print(f"Found duplicate fallback: ID={r.fallback_id}, Model={r.model_name}, Purpose={r.purpose}")
                duplicates_to_delete.append(r.fallback_id)
            else:
                seen.add(key)

        if duplicates_to_delete:
            for fid in duplicates_to_delete:
                conn.execute(
                    text("DELETE FROM llm_fallbacks WHERE fallback_id = :fid"),
                    {"fid": fid}
                )
            print(f"Successfully deleted {len(duplicates_to_delete)} duplicate fallback entries.")
        else:
            print("No duplicate fallbacks found in the database.")

if __name__ == "__main__":
    cleanup()
