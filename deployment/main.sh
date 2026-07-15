#!/usr/bin/env bash

###############################################################################
# Retail AI Platform
# Initial Server Setup
###############################################################################

set -e

PROJECT_DIR="/opt/retail-ai"
REPO_URL="https://github.com/AathiganapathiK/Single-Tenant-Ai-Conversational-Bot.git"

echo "========================================================"
echo "Retail AI Platform - Initial Server Setup"
echo "========================================================"

###############################################################################
# Update Ubuntu
###############################################################################

echo
echo "[1/5] Updating Ubuntu..."

sudo apt update
sudo apt upgrade -y

###############################################################################
# Clone Repository
###############################################################################

echo
echo "[2/5] Cloning Git Repository..."

if [ ! -d "$PROJECT_DIR" ]; then
    sudo mkdir -p "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"

if [ ! -d ".git" ]; then
    sudo git clone "$REPO_URL" .
else
    echo "Repository already exists. Pulling latest changes..."
    sudo git pull
fi

###############################################################################
# Make Scripts Executable
###############################################################################

echo
echo "[3/5] Making deployment scripts executable..."

cd deployment

sudo chmod +x *.sh

###############################################################################
# Display Next Steps
###############################################################################

echo
echo "========================================================"
echo "Initial Setup Completed Successfully"
echo "========================================================"

echo
echo "Next run the deployment scripts one by one:"
echo
echo "sudo ./01_setup_server.sh"
echo "sudo ./02_install_sqlserver.sh"
echo "sudo ./03_restore_database.sh"
echo "sudo ./04_run_migrations.sh"
echo "sudo ./05_install_backend.sh"
echo "sudo ./06_install_frontend.sh"
echo "sudo ./07_configure_backend.sh"
echo "sudo ./08_configure_nginx.sh"
echo "sudo ./10_start_services.sh"
echo "sudo ./09_verify_installation.sh"

echo
echo "========================================================"
