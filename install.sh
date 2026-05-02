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
if command -v pkg &> /dev/null; then
    pkg install -y python-tkinter python-gobject webkit2gtk-4.0 xdg-utils
elif command -v apt-get &> /dev/null; then
    sudo apt-get update
    sudo apt-get install -y python3-tk
fi

echo ""
echo "[3/4] Installing Python dependencies..."
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
