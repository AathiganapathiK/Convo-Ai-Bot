#!/usr/bin/env bash

###############################################################################
# Retail AI Deployment
# Step 05 - Install Backend
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/deployment.conf"

print_header "05 - Install Backend"

require_root
check_internet

require_directory "$BACKEND_DIR"
cd "$BACKEND_DIR"

if ! command_exists "$PYTHON_BIN"; then
    error "Python is not installed."
fi

PYTHON_VERSION=$($PYTHON_BIN --version)
success "$PYTHON_VERSION detected."

if [[ -d "$VENV_NAME" ]]; then
    success "Virtual Environment already exists."
else
    info "Creating Virtual Environment..."
    "$PYTHON_BIN" -m venv "$VENV_NAME"
    success "Virtual Environment Created."
fi

source "$VENV_NAME/bin/activate"
success "Virtual Environment Activated."

info "Upgrading pip..."
pip install --upgrade pip

require_file "requirements.txt"

info "Installing Python Packages..."
pip install -r requirements.txt
success "Python Packages Installed."

require_file "app.py"

if python -c "import uvicorn" >/dev/null 2>&1; then success "uvicorn OK"; else error "uvicorn import failed."; fi
if python -c "import fastapi" >/dev/null 2>&1; then success "FastAPI OK"; else error "FastAPI import failed."; fi
if python -c "import sqlalchemy" >/dev/null 2>&1; then success "SQLAlchemy OK"; else error "SQLAlchemy import failed."; fi
if python -c "import pyodbc" >/dev/null 2>&1; then success "PyODBC OK"; else error "PyODBC import failed."; fi
if python -c "import groq" >/dev/null 2>&1; then success "Groq SDK OK"; else error "Groq SDK import failed."; fi

# NOTE: importing app here will only succeed once backend/.env exists with
# valid DB credentials (see 07_configure_backend.sh, which runs AFTER this).
# So we don't hard-fail here — we just warn if .env isn't ready yet.
if [[ -f ".env" ]]; then
    info "Validating backend startup..."
    if python -c "import app" >/dev/null 2>&1; then
        success "Backend imports successfully."
    else
        warning "Backend import failed — check .env values once 07_configure_backend.sh has run."
    fi
else
    warning ".env not found yet — backend import check will happen after 07_configure_backend.sh."
fi

summary \
"Backend Directory Verified" \
"Virtual Environment Ready" \
"Python Packages Installed"

print_footer "Backend Installation Completed"
