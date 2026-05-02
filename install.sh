#!/bin/bash
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Freaker Installer v1.0.0"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "[1/4] Updating package lists..."
if command -v pkg &> /dev/null; then
    pkg update -y
fi

echo ""
echo "[2/4] Installing system packages..."

echo ""
echo "[3/4] Installing Python dependencies..."
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo ""
echo "[4/4] Setting up launch script..."
chmod +x launch.sh
chmod +x update.sh

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Installation complete!"
echo "  Launch: ./launch.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
