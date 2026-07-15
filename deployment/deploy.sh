#!/usr/bin/env bash
# sudo ./deploy.sh

###############################################################################
# Retail AI Deployment
# Master Deployment Script
###############################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/deployment.conf"

print_header "Retail AI Full Deployment"

require_root

SCRIPTS=(
    "01_setup_server.sh"
    "02_install_sqlserver.sh"
    "03_restore_database.sh"
    "04_run_migrations.sh"
    "05_install_backend.sh"
    "06_install_frontend.sh"
    "07_configure_backend.sh"
    "08_configure_nginx.sh"
    "09_verify_installation.sh"
    "10_start_services.sh"
)

echo
info "Checking deployment scripts..."

for SCRIPT in "${SCRIPTS[@]}"
do
    if [[ ! -f "$SCRIPT_DIR/$SCRIPT" ]]; then
        error "Missing deployment script: $SCRIPT"
    fi
done

success "All deployment scripts found."

START_TIME=$(date +%s)

TOTAL=${#SCRIPTS[@]}
CURRENT=1

for SCRIPT in "${SCRIPTS[@]}"
do
    echo
    echo "============================================================"
    echo "Step $CURRENT of $TOTAL"
    echo "$SCRIPT"
    echo "============================================================"

    chmod +x "$SCRIPT_DIR/$SCRIPT"

    if "$SCRIPT_DIR/$SCRIPT"
    then
        success "$SCRIPT completed successfully."
    else
        error "$SCRIPT failed. Deployment aborted."
    fi

    CURRENT=$((CURRENT+1))
done

END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME-START_TIME))

SERVER_IP=$(hostname -I | awk '{print $1}')

echo
echo "============================================================"
echo "Retail AI Deployment Completed Successfully"
echo "============================================================"
echo "Project           : $PROJECT_NAME"
echo "Installation Path : $INSTALL_ROOT"
echo "Frontend URL      : http://$SERVER_IP"
echo "Backend URL       : http://$SERVER_IP:$BACKEND_PORT"
if [[ "$SQL_IS_LOCAL" == "true" ]]; then
    echo "SQL Server        : localhost:$SQL_PORT"
else
    echo "SQL Server        : $SQL_HOST:$SQL_PORT (remote)"
fi
echo
echo "Total Deployment Time : ${TOTAL_TIME} seconds"
echo "============================================================"

summary \
"Ubuntu Configured" \
"SQL Server / ODBC Ready" \
"Databases Restored" \
"Migrations Applied" \
"Backend Installed" \
"Frontend Installed" \
"Nginx Configured" \
"Services Started"

print_footer "Deployment Finished"
