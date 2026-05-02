#!/bin/bash
# Simple launch script for Freaker

if [ -f "src/app.py" ]; then
    source venv/bin/activate
    python3 src/app.py "$@"
else
    echo "Error: src/app.py not found. Are you in the right directory?"
    exit 1
fi
