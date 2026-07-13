import os
import re
import sys
import logging
from sqlalchemy import text, inspect

# Add backend directory to path if run from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("migration_runner")

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")

MIGRATION_FILES = [
    "001_security_framework.sql",
    "002_semantic_audit_types.sql",
    "003_column_display_config.sql"
]

def ensure_migration_table():
    with engine.begin() as conn:
        inspector = inspect(engine)
        if not inspector.has_table("__schema_migrations"):
            logger.info("Creating __schema_migrations table...")
            conn.execute(text("""
                CREATE TABLE __schema_migrations (
                    migration_name NVARCHAR(255) PRIMARY KEY,
                    applied_at DATETIME DEFAULT GETDATE()
                )
            """))
            logger.info("__schema_migrations table created successfully.")

def get_applied_migrations():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT migration_name FROM __schema_migrations"))
        return {row[0] for row in result.fetchall()}

def record_migration(migration_name):
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO __schema_migrations (migration_name) VALUES (:name)"),
            {"name": migration_name}
        )

def run_sql_script(filepath):
    logger.info(f"Reading migration file: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by SQL Server 'GO' batch separators
    # Split on lines containing only 'GO' (ignoring whitespace and case)
    batches = re.split(r'(?i)^\s*GO\s*$', content, flags=re.MULTILINE)
    
    with engine.begin() as conn:
        for batch in batches:
            clean_batch = batch.strip()
            if not clean_batch:
                continue
            
            # Remove leading/trailing comments and print statements from log, then execute
            try:
                conn.execute(text(clean_batch))
            except Exception as e:
                logger.error(f"Error executing SQL batch starting with:\n{clean_batch[:200]}...")
                raise e

def main():
    logger.info("Starting database migrations...")
    try:
        ensure_migration_table()
    except Exception as e:
        logger.error(f"Failed to check/create migration tracking table: {e}")
        sys.exit(1)

    try:
        applied = get_applied_migrations()
    except Exception as e:
        logger.error(f"Failed to retrieve list of applied migrations: {e}")
        sys.exit(1)

    logger.info(f"Found {len(applied)} already applied migrations.")

    applied_count = 0
    skipped_count = 0

    for migration in MIGRATION_FILES:
        if migration in applied:
            logger.info(f"Migration {migration} is already applied. Skipping.")
            skipped_count += 1
            continue

        filepath = os.path.join(MIGRATIONS_DIR, migration)
        if not os.path.exists(filepath):
            logger.warning(f"Migration file not found: {filepath}. Skipping.")
            skipped_count += 1
            continue

        logger.info(f"Applying migration: {migration}")
        try:
            run_sql_script(filepath)
            record_migration(migration)
            logger.info(f"Successfully applied: {migration}")
            applied_count += 1
        except Exception as e:
            logger.error(f"Migration {migration} failed to apply: {e}")
            sys.exit(1)

    logger.info("=== Migration Summary ===")
    logger.info(f"Migrations Applied: {applied_count}")
    logger.info(f"Migrations Skipped: {skipped_count}")
    logger.info("Database migrations check completed successfully.")

if __name__ == "__main__":
    main()
