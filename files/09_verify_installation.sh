#!/usr/bin/env bash

###############################################################################
# Retail AI Deployment
# Step 09 - Verify Installation
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/deployment.conf"

print_header "09 - Verify Installation"

FAILED=0

verify() {
    DESCRIPTION=$1
    COMMAND=$2
    printf "%-45s" "$DESCRIPTION"
    if eval "$COMMAND" >/dev/null 2>&1
    then
        echo "[PASS]"
    else
        echo "[FAIL]"
        FAILED=$((FAILED+1))
    fi
}

verify "Ubuntu Installed" "grep -q Ubuntu /etc/os-release"
verify "Python Installed" "command -v python3"
verify "Virtual Environment Exists" "[ -d \"$BACKEND_DIR/$VENV_NAME\" ]"
verify "Node.js Installed" "command -v node"
verify "npm Installed" "command -v npm"

if [[ "$SQL_IS_LOCAL" == "true" ]]; then
    verify "SQL Server Service (local)" "systemctl is-active --quiet $SQL_SERVICE_NAME"
else
    printf "%-45s" "SQL Server Service (remote — skipped)"
    echo "[SKIP]"
fi

verify "sqlcmd Installed" "command -v sqlcmd"
verify "Backend Directory" "[ -d \"$BACKEND_DIR\" ]"
verify "requirements.txt" "[ -f \"$BACKEND_DIR/requirements.txt\" ]"
verify "app.py" "[ -f \"$BACKEND_DIR/app.py\" ]"
verify "Backend .env" "[ -f \"$BACKEND_ENV_FILE\" ]"
verify "Frontend Directory" "[ -d \"$FRONTEND_DIR\" ]"
verify "package.json" "[ -f \"$FRONTEND_DIR/package.json\" ]"
verify "React Build" "[ -d \"$FRONTEND_DIR/$FRONTEND_BUILD_DIR\" ]"
verify "Nginx Installed" "command -v nginx"
verify "Nginx Running" "systemctl is-active --quiet nginx"
verify "Nginx Config" "[ -f /etc/nginx/sites-available/$NGINX_SITE_NAME ]"
verify "Backend Service File" "[ -f /etc/systemd/system/$SYSTEMD_SERVICE_NAME.service ]"
verify "Backend Port $BACKEND_PORT" "ss -tuln | grep -q :$BACKEND_PORT"
verify "HTTP Port 80" "ss -tuln | grep -q ':80 '"
verify "GROQ_API_KEY set" "grep -q '^GROQ_API_KEY=' $BACKEND_ENV_FILE"
verify "AUTH0_DOMAIN set" "grep -q '^AUTH0_DOMAIN=' $BACKEND_ENV_FILE"
verify "AUTH0_AUDIENCE set" "grep -q '^AUTH0_AUDIENCE=' $BACKEND_ENV_FILE"
verify "DB_HOST set" "grep -q '^DB_HOST=' $BACKEND_ENV_FILE"
verify "DB_USER set" "grep -q '^DB_USER=' $BACKEND_ENV_FILE"
verify "DB_PASSWORD set" "grep -q '^DB_PASSWORD=' $BACKEND_ENV_FILE"
verify "DB_NAME set" "grep -q '^DB_NAME=' $BACKEND_ENV_FILE"

echo
echo "============================================================"

if [[ $FAILED -eq 0 ]]
then
    success "All deployment verification checks passed."
else
    warning "$FAILED verification check(s) failed."
fi

echo "============================================================"

print_footer "Verification Completed"

exit $FAILED
