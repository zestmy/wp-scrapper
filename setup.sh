#!/usr/bin/env bash
# setup.sh — DigitalOcean droplet install script for WP Scrapper
# Usage: curl -sSL https://raw.githubusercontent.com/zestmy/wp-scrapper/main/setup.sh | bash

set -euo pipefail

REPO_URL="https://github.com/zestmy/wp-scrapper.git"
INSTALL_DIR="/opt/ifranchise-scraper"
VENV_DIR="${INSTALL_DIR}/venv"
LOG_FILE="${INSTALL_DIR}/scraper.log"
CRON_SCHEDULE="0 8 * * *"

echo "=== WP Scrapper — Setup Script ==="
echo "Install dir: ${INSTALL_DIR}"

# --- System dependencies ---
echo "[1/5] Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git > /dev/null

# --- Clone or pull repo ---
echo "[2/5] Setting up repository..."
if [ -d "${INSTALL_DIR}/.git" ]; then
    echo "  Repo exists, pulling latest..."
    cd "${INSTALL_DIR}"
    git pull origin main
else
    echo "  Cloning fresh..."
    rm -rf "${INSTALL_DIR}"
    git clone "${REPO_URL}" "${INSTALL_DIR}"
    cd "${INSTALL_DIR}"
fi

# --- Virtual environment ---
echo "[3/5] Setting up Python virtual environment..."
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# --- Output directory ---
echo "[4/5] Creating output directory..."
mkdir -p "${INSTALL_DIR}/output"

# --- Cron job ---
echo "[5/5] Setting up cron job (daily at 8AM)..."
CRON_CMD="cd ${INSTALL_DIR} && ${VENV_DIR}/bin/python scraper.py >> ${LOG_FILE} 2>&1"

# Remove existing cron entry if present, then add fresh
(crontab -l 2>/dev/null | grep -v "ifranchise-scraper" || true) | crontab -
(crontab -l 2>/dev/null; echo "${CRON_SCHEDULE} ${CRON_CMD}") | crontab -

echo ""
echo "=== Setup Complete ==="
echo "  Install dir : ${INSTALL_DIR}"
echo "  Venv        : ${VENV_DIR}"
echo "  Output      : ${INSTALL_DIR}/output/"
echo "  Log         : ${LOG_FILE}"
echo "  Cron        : ${CRON_SCHEDULE} (daily at 8AM)"
echo ""
echo "Test manually: cd ${INSTALL_DIR} && ${VENV_DIR}/bin/python scraper.py"
