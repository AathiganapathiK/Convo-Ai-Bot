#!/usr/bin/env bash

###############################################################################
# Retail AI Deployment
# Step 03 - Restore SQL Server Databases
###############################################################################
# IMPORTANT if SQL_IS_LOCAL=false (SQL Server on a separate machine):
# SQL Server reads backup files from ITS OWN disk, not from wherever sqlcmd
# is run. You must copy the .bak files onto the database server itself
# (or a network path it can read) BEFORE running this script, and set
# DATABASE_BACKUP_DIR to a path valid on that server, and adjust
# DATA_FILE/LOG_FILE destination paths below to match that server's SQL
# Server data directory (ask your mentor: SELECT SERVERPROPERTY('InstanceDefaultDataPath')).
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/deployment.conf"

print_header "03 - Restore SQL Server Databases"

if [[ "$SQL_IS_LOCAL" != "true" ]]; then
    warning "SQL_IS_LOCAL=false: this script assumes .bak files are ALREADY present"
    warning "on the remote SQL Server's own disk at: $DATABASE_BACKUP_DIR"
    warning "If that path is not valid on the remote server, this will fail."
fi

###############################################################################
# Validate Backup Directory (only meaningful check when SQL_IS_LOCAL=true;
# when false we cannot check the remote filesystem from here)
###############################################################################

if [[ "$SQL_IS_LOCAL" == "true" ]]; then
    mkdir -p "$DATABASE_BACKUP_DIR"
    if [[ ! -d "$DATABASE_BACKUP_DIR" ]]; then
        error "Backup directory not found: $DATABASE_BACKUP_DIR"
    fi
fi

###############################################################################
# Check sqlcmd
###############################################################################

if ! command_exists sqlcmd; then
    error "sqlcmd is not installed. Run 02_install_sqlserver.sh first."
fi

###############################################################################
# SQL Admin Credentials
###############################################################################

echo
read -p "SQL Server admin username [$SQL_ADMIN_USER]: " INPUT_USER
SQL_USER="${INPUT_USER:-$SQL_ADMIN_USER}"

read -s -p "Enter SQL Server password for $SQL_USER: " SQL_PASSWORD
echo

###############################################################################
# Test Connection First
###############################################################################

if ! sqlcmd -S "$SQL_HOST,$SQL_PORT" -U "$SQL_USER" -P "$SQL_PASSWORD" -Q "SELECT 1;" >/dev/null 2>&1; then
    error "Could not connect to SQL Server at $SQL_HOST,$SQL_PORT with user $SQL_USER. Check credentials/firewall."
fi

success "Connected to SQL Server at $SQL_HOST,$SQL_PORT."

###############################################################################
# Find Backup Files (local mode only — remote mode restores by expected names)
###############################################################################

if [[ "$SQL_IS_LOCAL" == "true" ]]; then
    BACKUPS=("$DATABASE_BACKUP_DIR"/*.bak)
    if [[ ! -e "${BACKUPS[0]}" ]]; then
        error "No .bak files found in $DATABASE_BACKUP_DIR"
    fi
else
    # Remote mode: restore the two known databases from their expected filenames
    BACKUPS=(
        "${DATABASE_BACKUP_DIR}/${PLATFORM_BACKUP_FILE}"
        "${DATABASE_BACKUP_DIR}/${CLIENT_BACKUP_FILE}"
    )
fi

###############################################################################
# Restore Loop
###############################################################################

RESTORED=0
SKIPPED=0

for BACKUP in "${BACKUPS[@]}"
do

    DB_NAME=$(basename "$BACKUP" .bak)

    info "Processing Database : $DB_NAME"

    EXISTS=$(sqlcmd \
        -S "$SQL_HOST,$SQL_PORT" \
        -U "$SQL_USER" \
        -P "$SQL_PASSWORD" \
        -h -1 \
        -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name='$DB_NAME';")

    EXISTS=$(echo "$EXISTS" | xargs)

    if [[ "$EXISTS" == "1" ]]; then
        warning "$DB_NAME already exists. Skipping (delete it manually first if you want a clean restore)."
        ((SKIPPED++))
        continue
    fi

    info "Reading backup metadata for $DB_NAME..."

    FILELIST=$(sqlcmd \
        -S "$SQL_HOST,$SQL_PORT" \
        -U "$SQL_USER" \
        -P "$SQL_PASSWORD" \
        -Q "RESTORE FILELISTONLY FROM DISK=N'$BACKUP';")

    if [[ -z "$FILELIST" ]]; then
        warning "Could not read backup metadata for $BACKUP. Is the file present ON THE SQL SERVER's disk? Skipping."
        continue
    fi

    LOGICAL_DATA=$(echo "$FILELIST" | awk 'NR==3 {print $1}')
    LOGICAL_LOG=$(echo "$FILELIST" | awk 'NR==4 {print $1}')

    # Default SQL Server on Linux data path. If your mentor's server uses a
    # different data directory, override DATA_FILE/LOG_FILE below.
    DATA_FILE="/var/opt/mssql/data/${DB_NAME}.mdf"
    LOG_FILE="/var/opt/mssql/data/${DB_NAME}_log.ldf"

    info "Restoring $DB_NAME..."

    sqlcmd \
        -S "$SQL_HOST,$SQL_PORT" \
        -U "$SQL_USER" \
        -P "$SQL_PASSWORD" \
        -Q "
RESTORE DATABASE [$DB_NAME]
FROM DISK=N'$BACKUP'
WITH
MOVE '$LOGICAL_DATA' TO '$DATA_FILE',
MOVE '$LOGICAL_LOG' TO '$LOG_FILE',
REPLACE;
"

    success "$DB_NAME restored."
    ((RESTORED++))

done

###############################################################################
# Verify
###############################################################################

echo
info "Available Databases"

sqlcmd \
-S "$SQL_HOST,$SQL_PORT" \
-U "$SQL_USER" \
-P "$SQL_PASSWORD" \
-Q "SELECT name FROM sys.databases;"

echo

summary \
"Databases Restored : $RESTORED" \
"Databases Skipped  : $SKIPPED"

print_footer "Database Restore Completed"
