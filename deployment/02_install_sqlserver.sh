#!/usr/bin/env bash

###############################################################################
# Retail AI Deployment
# Step 02 - Install SQL Server Engine + ODBC Client Tools
###############################################################################
# Confirmed setup: fresh install of SQL Server on this Ubuntu 24.04 machine
# (SQL_IS_LOCAL=true in deployment.conf). This installs the mssql-server
# engine itself, plus the ODBC Driver 18 + sqlcmd that your Python backend
# (pyodbc) needs to talk to it.
#
# NOTE ON SSMS: SQL Server Management Studio (SSMS) is Windows-only and
# cannot be installed on this Linux server. To browse the database visually,
# either (a) install SSMS on your mentor's Windows laptop and connect
# remotely to this server's IP over port 1433, or (b) use Azure Data Studio
# / the VS Code mssql extension, both of which run on Linux too.
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/common.sh"
source "$SCRIPT_DIR/deployment.conf"

print_header "02 - SQL Server Engine / ODBC Client Tools"

require_root
check_internet

###############################################################################
# Detect Ubuntu Version
###############################################################################

UBUNTU_VERSION=$(get_ubuntu_version)
info "Ubuntu Version : $UBUNTU_VERSION"

case "$UBUNTU_VERSION" in
    "22.04"|"24.04")
        success "Ubuntu version supported."
        ;;
    *)
        warning "Ubuntu $UBUNTU_VERSION is not explicitly verified for SQL Server. Proceeding anyway."
        ;;
esac

###############################################################################
# Detect CPU Architecture
###############################################################################

ARCH=$(get_architecture)
info "Architecture : $ARCH"

if [[ "$ARCH" != "x86_64" ]]; then
    error "Only x86_64 architecture is supported by SQL Server on Linux."
fi

###############################################################################
# Add Microsoft Repository (needed for ODBC driver + sqlcmd either way)
###############################################################################

REPO_LIST="/etc/apt/sources.list.d/mssql-release.list"
REPO_KEY="/usr/share/keyrings/microsoft-prod.gpg"

# Step 1: Add GPG key only if it doesn't already exist
if [[ ! -f "$REPO_KEY" ]]; then
    info "Downloading Microsoft GPG key..."
    
    TMPKEY=$(mktemp)
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o "$TMPKEY"
    
    # Move atomically to avoid corruption if download fails
    mv "$TMPKEY" "$REPO_KEY"
    success "Microsoft GPG key installed."
else
    success "Microsoft GPG key already present."
fi

# Step 2: Add repository list only if it doesn't already exist
if [[ ! -f "$REPO_LIST" ]]; then
    info "Adding Microsoft package repository list..."
    
    TMPLIST=$(mktemp)
    curl -fsSL https://packages.microsoft.com/config/ubuntu/${UBUNTU_VERSION}/prod.list \
        > "$TMPLIST"
    
    # Update repository entry to use the GPG key we just installed
    sed "s#deb #deb [signed-by=${REPO_KEY}] #" "$TMPLIST" > "${TMPLIST}.signed"
    
    # Move atomically
    mv "${TMPLIST}.signed" "$REPO_LIST"
    rm -f "$TMPLIST"
    success "Repository list added."
else
    success "Microsoft repository already configured."
fi

update_packages

###############################################################################
# SQL Server Engine (conditional)
###############################################################################

if [[ "$SQL_IS_LOCAL" == "true" ]]; then

    if command_exists sqlservr; then
        success "SQL Server engine already installed on this machine."
    else
        info "Installing Microsoft SQL Server (fresh install on Ubuntu $UBUNTU_VERSION)..."
        ACCEPT_EULA=Y apt-get install -y mssql-server
        success "SQL Server package installed."

        echo
        info "Running mssql-conf setup to configure the SA password and edition..."
        info "You will be prompted to choose an edition (Developer is free, recommended for non-production)"
        info "and to set the SA (system administrator) password. Remember this password —"
        info "you will need it for 03_restore_database.sh and 04_run_migrations.sh."
        echo

        /opt/mssql/bin/mssql-conf setup

        success "SQL Server configured."
    fi

else
    info "SQL_IS_LOCAL=false — SQL Server engine will not be installed on this machine."
    info "Make sure SQL_HOST in deployment.conf points to the correct remote database server."
fi

###############################################################################
# ODBC Driver 18 (always required by the Python backend, pyodbc)
###############################################################################

if is_package_installed msodbcsql18; then
    success "ODBC Driver 18 already installed."
else
    info "Installing ODBC Driver 18..."
    ACCEPT_EULA=Y apt-get install -y msodbcsql18
    success "ODBC Driver 18 installed."
fi

###############################################################################
# SQLCMD (always required for restore/migration steps)
###############################################################################

if command_exists sqlcmd; then
    success "sqlcmd already installed."
else
    info "Installing mssql-tools18..."
    ACCEPT_EULA=Y apt-get install -y mssql-tools18

    if ! grep -q "/opt/mssql-tools18/bin" ~/.bashrc; then
        echo 'export PATH="$PATH:/opt/mssql-tools18/bin"' >> ~/.bashrc
    fi

    export PATH="$PATH:/opt/mssql-tools18/bin"
    success "sqlcmd installed."
fi

###############################################################################
# Enable/Start Service (only if the engine is actually local)
###############################################################################

if [[ "$SQL_IS_LOCAL" == "true" ]] && command_exists sqlservr; then
    enable_service "$SQL_SERVICE_NAME"
    start_service "$SQL_SERVICE_NAME"
fi

###############################################################################
# Verify Connectivity to Configured SQL_HOST
###############################################################################

echo
info "Testing connectivity to SQL Server at ${SQL_HOST},${SQL_PORT} ..."

if command_exists sqlcmd; then
    read -s -p "Enter SQL Server admin password (for $SQL_ADMIN_USER) to test connection, or press Enter to skip: " TEST_PASSWORD
    echo
    if [[ -n "$TEST_PASSWORD" ]]; then
        if sqlcmd -S "${SQL_HOST},${SQL_PORT}" -U "$SQL_ADMIN_USER" -P "$TEST_PASSWORD" -Q "SELECT @@VERSION;" >/dev/null 2>&1; then
            success "Successfully connected to SQL Server at ${SQL_HOST},${SQL_PORT}."
        else
            warning "Could not connect to SQL Server at ${SQL_HOST},${SQL_PORT}. Check SQL_HOST, firewall rules, and credentials."
        fi
    else
        info "Skipped connectivity test."
    fi
fi

echo

summary \
"ODBC Driver 18 Ready" \
"SQLCMD Ready" \
"SQL Server Reachability Checked"

print_footer "SQL Server / ODBC Client Setup Completed"
