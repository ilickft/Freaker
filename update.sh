#!/bin/bash
set -e

echo "Updating Freaker..."

if [ -d ".git" ]; then
    git pull
else
    echo "No .git directory found, skipping git pull."
fi

echo "Updating dependencies..."
pip install -r requirements.txt

echo "Update complete!"
