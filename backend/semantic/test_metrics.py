# file: test_metrics.py
import sys
import os

# Ensure the backend project root is in the import path
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))  # backend folder
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from semantic.semantic_service import SemanticService

def main():
    # Try the hardcoded connection ID first
    active_connection_id = "D429651D-E193-4327-9669-764A84E0AC18"
    metrics = SemanticService.get_metrics(active_connection_id)
    
    # Fallback to active connection if hardcoded one yields no metrics
    if not metrics:
        from database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            row = conn.execute(text("SELECT connection_id FROM database_connections WHERE is_active = 1")).fetchone()
            if row:
                active_connection_id = str(row[0])
                metrics = SemanticService.get_metrics(active_connection_id)

    print("Metrics for connection_id =", active_connection_id)
    print(metrics)
    for row in metrics:
        print(row)

if __name__ == "__main__":
    main()
