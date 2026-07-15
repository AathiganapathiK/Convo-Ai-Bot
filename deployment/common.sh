#!/usr/bin/env bash

###############################################################################
# RR AI Chatbot Deployment Framework
# Common Utility Functions
###############################################################################

set -e

###############################################################################
# Colors
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

###############################################################################
# Logging
###############################################################################

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

###############################################################################
# Headers
###############################################################################

print_header() {
    clear
    echo "============================================================"
    echo "           Retail AI Deployment Framework"
    echo "============================================================"
    echo "Script : $1"
    echo "Started: $(date)"
    echo "============================================================"
    echo
}

print_footer() {
    echo
    echo "============================================================"
    success "$1"
    echo "Completed: $(date)"
    echo "============================================================"
}

###############################################################################
# Root Check
###############################################################################

require_root() {
    if [[ $EUID -ne 0 ]]; then
        error "Please run this script using sudo."
    fi
}

###############################################################################
# Ubuntu Version
###############################################################################

get_ubuntu_version() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        echo "$VERSION_ID"
    else
        error "Unable to determine Ubuntu version."
    fi
}

###############################################################################
# CPU Architecture
###############################################################################

get_architecture() {
    uname -m
}

###############################################################################
# Package Checks
###############################################################################

is_package_installed() {
    dpkg -s "$1" >/dev/null 2>&1
}

install_package() {
    PACKAGE=$1
    if is_package_installed "$PACKAGE"; then
        success "$PACKAGE already installed."
    else
        info "Installing $PACKAGE..."
        apt-get install -y "$PACKAGE"
        success "$PACKAGE installed."
    fi
}

###############################################################################
# Command Checks
###############################################################################

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

###############################################################################
# File Checks
###############################################################################

require_file() {
    FILE=$1
    if [[ ! -f "$FILE" ]]; then
        error "Required file not found: $FILE"
    fi
}

###############################################################################
# Directory Checks
###############################################################################

require_directory() {
    DIR=$1
    if [[ ! -d "$DIR" ]]; then
        error "Required directory not found: $DIR"
    fi
}

###############################################################################
# Service Checks
###############################################################################

service_exists() {
    systemctl list-unit-files | grep -q "^$1"
}

service_running() {
    systemctl is-active --quiet "$1"
}

start_service() {
    SERVICE=$1
    if service_running "$SERVICE"; then
        success "$SERVICE is already running."
    else
        info "Starting $SERVICE..."
        systemctl start "$SERVICE"
        success "$SERVICE started."
    fi
}

enable_service() {
    SERVICE=$1
    systemctl enable "$SERVICE" >/dev/null 2>&1
    success "$SERVICE enabled at boot."
}

###############################################################################
# Internet Connectivity
###############################################################################

check_internet() {
    if ping -c 1 google.com >/dev/null 2>&1; then
        success "Internet connection available."
    else
        error "No Internet connection detected."
    fi
}

###############################################################################
# Ubuntu Update
###############################################################################

update_packages() {
    info "Updating package index..."
    apt-get update
    success "Package index updated."
}

###############################################################################
# Script Summary
###############################################################################

summary() {
    echo
    echo "==================== SUMMARY ===================="
    for ITEM in "$@"
    do
        success "$ITEM"
    done
    echo "================================================="
}
