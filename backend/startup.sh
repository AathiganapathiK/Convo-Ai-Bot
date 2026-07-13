#!/usr/bin/env bash
set -e

echo "Starting backend boot sequence..."

# 1. Wait for Database availability (unless explicitly skipped)
if [ "$SKIP_DB_WAIT" = "true" ]; then
    echo "SKIP_DB_WAIT=true -> Skipping database availability check."
else
    python tools/wait_for_db.py
fi

# 2. Run Database Migrations
if [ "$SKIP_DB_WAIT" = "true" ]; then
    echo "Skipping database migrations."
else
    python tools/run_migrations.py
fi

# 3. Start FastAPI application
echo "Starting FastAPI application with Uvicorn..."
exec uvicorn app:app --host 0.0.0.0 --port 8000