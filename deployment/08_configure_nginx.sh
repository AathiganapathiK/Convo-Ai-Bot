#!/usr/bin/env bash

###############################################################################
# Retail AI Deployment
# Step 08 - Configure Nginx
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/deployment.conf"

print_header "08 - Configure Nginx"

require_root

if ! command_exists nginx; then
    error "Nginx is not installed."
fi
success "Nginx detected."

BUILD_PATH="${FRONTEND_DIR}/${FRONTEND_BUILD_DIR}"
require_directory "$BUILD_PATH"

mkdir -p "$NGINX_ROOT"
success "Web root ready."

info "Copying React build..."
cp -r "$BUILD_PATH"/* "$NGINX_ROOT"/
success "Frontend copied."

require_file "$SCRIPT_DIR/nginx.conf"

SITE_AVAILABLE="/etc/nginx/sites-available/${NGINX_SITE_NAME}"
SITE_ENABLED="/etc/nginx/sites-enabled/${NGINX_SITE_NAME}"

cp "$SCRIPT_DIR/nginx.conf" "$SITE_AVAILABLE"
success "Nginx configuration copied."

if [[ -L /etc/nginx/sites-enabled/default ]]; then
    rm -f /etc/nginx/sites-enabled/default
    success "Default site removed."
fi

if [[ ! -L "$SITE_ENABLED" ]]; then
    ln -s "$SITE_AVAILABLE" "$SITE_ENABLED"
    success "Retail AI site enabled."
else
    success "Retail AI site already enabled."
fi

info "Testing Nginx configuration..."
nginx -t
success "Nginx configuration valid."

systemctl restart nginx

if service_running nginx; then
    success "Nginx is running."
else
    error "Nginx failed to start."
fi

summary \
"Frontend Published" \
"Nginx Configured" \
"Nginx Running"

print_footer "Nginx Configuration Completed"
