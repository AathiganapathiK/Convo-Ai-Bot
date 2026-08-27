"""
Apply a migration rollback script, deliberately and one at a time.

Rollbacks are intentionally NOT part of run_migrations.py. Nothing should ever
undo a schema change automatically; it has to be a decision someone makes.

Usage, from the backend directory:

    python tools/run_rollback.py 004            # roll back migration 004
    python tools/run_rollback.py 004 --dry-run  # show what would run, change nothing

The script prints the target server and database and asks for confirmation
before touching anything, because the same command run in the wrong shell hits
the wrong environment.
"""

import os
import re
import sys
import glob
import logging

# The backend directory must be importable before core.config or database are
# imported, because this script is normally invoked as tools/run_rollback.py,
# which puts tools/ on sys.path rather than backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.config  # noqa: F401,E402  - loads the environment first
from sqlalchemy import text  # noqa: E402
from database import engine, _host, _name  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rollback_runner")

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations"
)


def find_rollback_script(prefix: str) -> str:
    pattern = os.path.join(MIGRATIONS_DIR, f"{prefix}_*_rollback.sql")
    matches = sorted(glob.glob(pattern))
    if not matches:
        logger.error(f"No rollback script found matching {prefix}_*_rollback.sql")
        sys.exit(1)
    if len(matches) > 1:
        logger.error(f"Ambiguous prefix {prefix}: {[os.path.basename(m) for m in matches]}")
        sys.exit(1)
    return matches[0]


def run_sql_script(filepath: str) -> None:
    """Execute a script as one transaction, splitting on GO batch separators."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    batches = re.split(r"(?i)^\s*GO\s*$", content, flags=re.MULTILINE)

    with engine.begin() as conn:
        for batch in batches:
            clean = batch.strip()
            if not clean:
                continue
            try:
                conn.execute(text(clean))
            except Exception:
                logger.error(f"Failed on batch starting:\n{clean[:200]}...")
                raise


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    prefix = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    script = find_rollback_script(prefix)

    print()
    print("=" * 62)
    print("  ROLLBACK")
    print(f"  script   : {os.path.basename(script)}")
    print(f"  server   : {_host}")
    print(f"  database : {_name}")
    print("=" * 62)

    if dry_run:
        with open(script, "r", encoding="utf-8") as f:
            print(f.read())
        print("[dry run] nothing was executed.")
        return

    answer = input(f"Type the database name ({_name}) to confirm: ").strip()
    if answer != _name:
        print("Confirmation did not match. Nothing was executed.")
        sys.exit(1)

    logger.info(f"Applying rollback: {os.path.basename(script)}")
    try:
        run_sql_script(script)
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        logger.error("The transaction was rolled back; the schema is unchanged.")
        sys.exit(1)

    logger.info("Rollback applied successfully.")
    logger.info("Re-run 'python tools/run_migrations.py' to reapply the migration.")


if __name__ == "__main__":
    main()
