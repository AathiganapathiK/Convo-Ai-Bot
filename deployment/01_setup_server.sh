#!/usr/bin/env bash

set -e

echo "========================================="
echo " Retail AI - Server Prerequisites Setup"
echo "========================================="

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script with sudo."
    exit 1
fi

echo ""
echo "Updating package index..."
apt-get update

install_if_missing() {
    PACKAGE=$1

    if dpkg -s "$PACKAGE" >/dev/null 2>&1; then
        echo "[OK] $PACKAGE already installed."
    else
        echo "[+] Installing $PACKAGE ..."
        apt-get install -y "$PACKAGE"
    fi
}

echo ""
echo "Installing common packages..."

PACKAGES=(
    git
    curl
    wget
    unzip
    zip
    build-essential
    software-properties-common
    python3
    python3-pip
    python3-venv
    python3-dev
    unixodbc
    unixodbc-dev
    nginx
)

for pkg in "${PACKAGES[@]}"
do
    install_if_missing "$pkg"
done

echo ""
echo "Checking Node.js..."

if command -v node >/dev/null 2>&1; then
    echo "[OK] Node.js $(node -v) already installed."
else
    echo "[+] Installing Node.js 20 LTS..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi

echo ""
echo "Checking npm..."

if command -v npm >/dev/null 2>&1; then
    echo "[OK] npm $(npm -v) already installed."
else
    echo "[+] Installing npm..."
    apt-get install -y npm
fi

echo ""
echo "========================================="
echo " Server prerequisite installation complete"
echo "========================================="
