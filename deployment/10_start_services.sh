#!/usr/bin/env bash

###############################################################################
# Retail AI Deployment
# Step 10 - Start Services
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/deployment.conf"

print_header "10 - Start Services"

require_root

###############################################################################
# SQL Server (only if it runs on this machine)
###############################################################################

if [[ "$SQL_IS_LOCAL" == "true" ]]; then
    info "Starting SQL Server..."
    systemctl start "$SQL_SERVICE_NAME"

    if service_running "$SQL_SERVICE_NAME"; then
        success "SQL Server is running."
    else
        error "SQL Server failed to start."
    fi
else
    info "SQL_IS_LOCAL=false — skipping local SQL Server start (it runs on $SQL_HOST)."
fi

###############################################################################
# Backend
###############################################################################

info "Starting Backend..."
systemctl start "${SYSTEMD_SERVICE_NAME}.service"

sleep 5

if service_running "${SYSTEMD_SERVICE_NAME}.service"; then
    success "Backend service is running."
else
    error "Backend service failed to start. Check: journalctl -u ${SYSTEMD_SERVICE_NAME}.service -n 50"
fi

###############################################################################
# Nginx
###############################################################################

info "Restarting Nginx..."
systemctl restart nginx

if service_running nginx; then
    success "Nginx is running."
else
    error "Nginx failed to start."
fi

###############################################################################
# Backend Health Check
###############################################################################

echo
info "Checking Backend Health..."

if curl -fs "http://${BACKEND_HOST}:${BACKEND_PORT}/" >/dev/null 2>&1; then
    success "Backend API reachable."
else
    warning "Backend started but health endpoint not reachable. Check DB_HOST/DB_USER/DB_PASSWORD in .env"
    warning "and confirm the SQL Server firewall allows connections from this machine."
fi

SERVER_IP=$(hostname -I | awk '{print $1}')

echo
echo "============================================================"
echo "Retail AI Platform Started"
echo "============================================================"
echo "Frontend : http://${SERVER_IP}"
echo "Backend  : http://${SERVER_IP}:${BACKEND_PORT}"
echo "Nginx    : Running"
if [[ "$SQL_IS_LOCAL" == "true" ]]; then
    echo "SQL      : Running (local)"
else
    echo "SQL      : Remote at ${SQL_HOST}"
fi
echo "============================================================"

summary \
"Backend Started" \
"Nginx Started"

print_footer "Retail AI Deployment Completed"
