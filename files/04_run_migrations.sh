#!/usr/bin/env bash

###############################################################################
# Retail AI Deployment
# Step 04 - Run Database Migrations
###############################################################################
# NOTE: This script was completely empty in the original file set.
# It now applies backend/migrations/*.sql against the PLATFORM_DATABASE,
# tracking what has already been applied in a __schema_migrations table so
# it is safe to re-run (e.g. if your restored .bak already contains these
# changes, they will be skipped rather than re-applied).
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/deployment.conf"

print_header "04 - Run Database Migrations"

if ! command_exists sqlcmd; then
    error "sqlcmd is not installed. Run 02_install_sqlserver.sh first."
fi

require_directory "$MIGRATION_DIR"

###############################################################################
# SQL Admin Credentials
###############################################################################

echo
read -p "SQL Server admin username [$SQL_ADMIN_USER]: " INPUT_USER
SQL_USER="${INPUT_USER:-$SQL_ADMIN_USER}"

read -s -p "Enter SQL Server password for $SQL_USER: " SQL_PASSWORD
echo

if ! sqlcmd -S "$SQL_HOST,$SQL_PORT" -U "$SQL_USER" -P "$SQL_PASSWORD" -Q "SELECT 1;" >/dev/null 2>&1; then
    error "Could not connect to SQL Server at $SQL_HOST,$SQL_PORT with user $SQL_USER."
fi

success "Connected to SQL Server at $SQL_HOST,$SQL_PORT."

###############################################################################
# Ensure Tracking Table Exists
###############################################################################

info "Ensuring __schema_migrations tracking table exists in $PLATFORM_DATABASE..."

sqlcmd -S "$SQL_HOST,$SQL_PORT" -U "$SQL_USER" -P "$SQL_PASSWORD" -d "$PLATFORM_DATABASE" -Q "
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = '__schema_migrations')
BEGIN
    CREATE TABLE __schema_migrations (
        migration_name NVARCHAR(255) PRIMARY KEY,
        applied_at DATETIME2 DEFAULT SYSDATETIME()
    );
END
" || error "Failed to create/verify __schema_migrations table."

###############################################################################
# Apply Migrations In Order
###############################################################################

MIGRATIONS=("$MIGRATION_1" "$MIGRATION_2")

APPLIED=0
SKIPPED=0

for MIGRATION_FILE in "${MIGRATIONS[@]}"
do

    FULL_PATH="${MIGRATION_DIR}/${MIGRATION_FILE}"

    if [[ ! -f "$FULL_PATH" ]]; then
        warning "Migration file not found, skipping: $FULL_PATH"
        continue
    fi

    ALREADY_APPLIED=$(sqlcmd -S "$SQL_HOST,$SQL_PORT" -U "$SQL_USER" -P "$SQL_PASSWORD" -d "$PLATFORM_DATABASE" -h -1 \
        -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM __schema_migrations WHERE migration_name = '$MIGRATION_FILE';")

    ALREADY_APPLIED=$(echo "$ALREADY_APPLIED" | xargs)

    if [[ "$ALREADY_APPLIED" == "1" ]]; then
        warning "$MIGRATION_FILE already applied. Skipping."
        ((SKIPPED++))
        continue
    fi

    info "Applying $MIGRATION_FILE ..."

    if sqlcmd -S "$SQL_HOST,$SQL_PORT" -U "$SQL_USER" -P "$SQL_PASSWORD" -d "$PLATFORM_DATABASE" -i "$FULL_PATH"; then

        sqlcmd -S "$SQL_HOST,$SQL_PORT" -U "$SQL_USER" -P "$SQL_PASSWORD" -d "$PLATFORM_DATABASE" -Q "
        INSERT INTO __schema_migrations (migration_name) VALUES ('$MIGRATION_FILE');
        " >/dev/null

        success "$MIGRATION_FILE applied."
        ((APPLIED++))

    else
        error "$MIGRATION_FILE failed to apply. Deployment aborted so you can inspect the error above."
    fi

done

echo

summary \
"Migrations Applied : $APPLIED" \
"Migrations Skipped : $SKIPPED"

print_footer "Database Migrations Completed"
