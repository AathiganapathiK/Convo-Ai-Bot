#!/usr/bin/env bash
set -e

echo "============================================================"
echo "Starting backend boot sequence..."
echo "============================================================"

echo ""
echo "===== Runtime Environment ====="
echo "APP_RUNTIME=${APP_RUNTIME}"
echo "HOST=${HOST}"
echo "PORT=${PORT}"
echo "PWD=$(pwd)"
echo ""

echo "===== Application Directory ====="
ls -la
echo ""

echo "===== Environment Files ====="
find . -maxdepth 2 -name "*.env" -o -name ".*.env"
echo ""

echo "===== Python Environment ====="
python --version
echo ""

echo "===== Loading Config Test ====="
python - <<'EOF'
import os

print("APP_RUNTIME before imports:", os.getenv("APP_RUNTIME"))

try:
    from core.config import runtime
    print("Runtime selected:", runtime)
    print("DB_HOST:", os.getenv("DB_HOST"))
    print("DB_PORT:", os.getenv("DB_PORT"))
    print("DB_NAME:", os.getenv("DB_NAME"))
except Exception as e:
    print("CONFIG LOAD FAILED:")
    import traceback
    traceback.print_exc()
    raise
EOF

echo ""
echo "===== Waiting for Database ====="

if [ "$SKIP_DB_WAIT" = "true" ]; then
    echo "Skipping database wait."
else
    python -m tools.wait_for_db
fi

echo ""
echo "===== Running Migrations ====="

if [ "$SKIP_DB_WAIT" = "true" ]; then
    echo "Skipping migrations."
else
    python -m tools.run_migrations
fi

echo ""
echo "===== Starting FastAPI ====="

exec uvicorn app:app --host 0.0.0.0 --port 8000