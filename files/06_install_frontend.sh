#!/usr/bin/env bash

###############################################################################
# Retail AI Deployment
# Step 06 - Install & Build Frontend
###############################################################################
# FIX: The original script order built the frontend BEFORE the backend/frontend
# .env files were configured (that happened later, in step 07). Create React
# App bakes REACT_APP_* variables into the build AT BUILD TIME — so the .env
# must exist and be correct BEFORE `npm run build` runs, or the built app
# will silently fall back to hardcoded localhost URLs. This script now
# creates frontend/.env from the template FIRST.
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/deployment.conf"

print_header "06 - Install & Build Frontend"

require_root
check_internet

require_directory "$FRONTEND_DIR"
cd "$FRONTEND_DIR"

###############################################################################
# Create frontend/.env BEFORE building (see note above)
###############################################################################

if [[ ! -f "$FRONTEND_ENV_FILE" ]]; then

    if [[ -f "$SCRIPT_DIR/frontend.env.example" ]]; then
        info "Creating frontend .env from template..."
        cp "$SCRIPT_DIR/frontend.env.example" "$FRONTEND_ENV_FILE"
        warning "Edit $FRONTEND_ENV_FILE now and set REACT_APP_API_BASE_URL to this server's real address"
        warning "(e.g. http://<server-ip>/api or https://yourdomain.com/api), then re-run this script."
        error "Stopping so you can configure $FRONTEND_ENV_FILE before the build bakes in the wrong URL."
    else
        error "frontend.env.example not found in $SCRIPT_DIR."
    fi

else
    success "frontend/.env already exists — using it as-is."
    info "Current REACT_APP_API_BASE_URL:"
    grep "^REACT_APP_API_BASE_URL=" "$FRONTEND_ENV_FILE" || warning "REACT_APP_API_BASE_URL not set in .env!"
fi

###############################################################################
# Node / npm Checks
###############################################################################

if ! command_exists node; then
    error "Node.js is not installed."
fi
NODE_VERSION=$(node -v)
success "Node.js Version : $NODE_VERSION"

if ! command_exists npm; then
    error "npm is not installed."
fi
NPM_VERSION=$(npm -v)
success "npm Version : $NPM_VERSION"

require_file "package.json"

if [[ -d "$FRONTEND_BUILD_DIR" ]]; then
    info "Removing previous build..."
    rm -rf "$FRONTEND_BUILD_DIR"
    success "Previous build removed."
fi

if [[ -d "node_modules" ]]; then
    success "node_modules already exists."
else
    info "Installing npm packages..."
    npm install
    success "npm packages installed."
fi

info "Verifying React installation..."
npm list react >/dev/null 2>&1
success "React verified."

info "Verifying react-scripts..."
npm list react-scripts >/dev/null 2>&1
success "react-scripts verified."

info "Building React Application..."
npm run build

if [[ ! -d "$FRONTEND_BUILD_DIR" ]]; then
    error "Build folder was not generated."
fi
success "Build folder created."

require_file "$FRONTEND_BUILD_DIR/index.html"
success "index.html verified."

BUILD_SIZE=$(du -sh "$FRONTEND_BUILD_DIR" | cut -f1)

echo
echo "============================================================"
echo "Frontend Build Summary"
echo "============================================================"
echo "Frontend Directory : $FRONTEND_DIR"
echo "Build Directory    : $FRONTEND_BUILD_DIR"
echo "Node Version       : $NODE_VERSION"
echo "NPM Version        : $NPM_VERSION"
echo "Build Size         : $BUILD_SIZE"
echo "============================================================"

summary \
"Frontend .env Configured" \
"Frontend Dependencies Installed" \
"React Build Successful"

print_footer "Frontend Installation Completed"
