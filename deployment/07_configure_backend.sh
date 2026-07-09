#!/usr/bin/env bash

###############################################################################
# Retail AI Deployment
# Step 07 - Configure Backend
###############################################################################
# Does the following:
# - Creates backend/.env from backend.env.example if it doesn't exist.
# - Validates every required environment variable is present.
# - Sets correct ownership.
# - Installs the systemd service (retail-ai-backend.service).
# - Enables the service to start on boot.
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/deployment.conf"

print_header "07 - Configure Backend"

require_root
require_directory "$BACKEND_DIR"
cd "$BACKEND_DIR"

###############################################################################
# Environment File
###############################################################################

if [[ ! -f "$BACKEND_ENV_FILE" ]]; then

    if [[ -f "$SCRIPT_DIR/backend.env.example" ]]; then
        info "Creating backend .env from template..."
        cp "$SCRIPT_DIR/backend.env.example" "$BACKEND_ENV_FILE"
        warning "Edit $BACKEND_ENV_FILE now with real values (DB_HOST, DB_USER, DB_PASSWORD,"
        warning "GROQ_API_KEY, AUTH0_DOMAIN, AUTH0_AUDIENCE, ENCRYPTION_KEY) then re-run this script."
        error "Stopping so you can fill in $BACKEND_ENV_FILE before continuing."
    else
        error "backend.env.example not found."
    fi

else
    success ".env already exists."
fi

###############################################################################
# Validate Required Environment Variables
###############################################################################

info "Validating environment configuration..."

REQUIRED_VARS=(
    GROQ_API_KEY
    ENCRYPTION_KEY
    DB_HOST
    DB_NAME
    DB_USER
    DB_PASSWORD
    DB_DRIVER
    AUTH0_DOMAIN
    AUTH0_AUDIENCE
)

MISSING=0

for VAR in "${REQUIRED_VARS[@]}"
do
    if ! grep -q "^${VAR}=" "$BACKEND_ENV_FILE"; then
        warning "$VAR is missing from $BACKEND_ENV_FILE."
        ((MISSING++))
    fi
done

# Also warn (not fail) if any value looks like it was left as a placeholder
for VAR in DB_PASSWORD GROQ_API_KEY ENCRYPTION_KEY; do
    VALUE=$(grep "^${VAR}=" "$BACKEND_ENV_FILE" | cut -d'=' -f2-)
    if [[ -z "$VALUE" || "$VALUE" == "changeme" || "$VALUE" == "your_"* ]]; then
        warning "$VAR looks unset or still a placeholder in $BACKEND_ENV_FILE."
    fi
done

if [[ $MISSING -gt 0 ]]; then
    error "$MISSING required environment variables are missing. Fix $BACKEND_ENV_FILE and re-run."
fi

success "Environment validation successful."

###############################################################################
# Permissions
###############################################################################

info "Setting ownership..."
chown -R "$DEPLOY_USER:$DEPLOY_GROUP" "$INSTALL_ROOT"
chmod 600 "$BACKEND_ENV_FILE"
success "Ownership and permissions configured."

###############################################################################
# Create Systemd Service
###############################################################################

SERVICE_TEMPLATE="$SCRIPT_DIR/retail-ai-backend.service"
require_file "$SERVICE_TEMPLATE"

cp "$SERVICE_TEMPLATE" "/etc/systemd/system/${SYSTEMD_SERVICE_NAME}.service"

systemctl daemon-reload
enable_service "${SYSTEMD_SERVICE_NAME}.service"

summary \
"Backend Environment Configured" \
"Systemd Service Installed" \
"Backend Ready"

print_footer "Backend Configuration Completed"
