#!/usr/bin/env bash
set -euo pipefail

# Create and activate virtual environment `.venv` and install Python deps
PYTHON=${PYTHON:-python3}
VENV_DIR=".venv"

echo "Using python: $(which $PYTHON)"

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment in $VENV_DIR"
  $PYTHON -m venv "$VENV_DIR"
fi

# Activate the venv in this script for pip installs
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

echo "Installing Python packages from requirements.txt"
if [ -f requirements.txt ]; then
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
else
  echo "requirements.txt not found, skipping Python package install"
fi

# Install npm deps locally
if [ -f package.json ]; then
  echo "Installing npm packages (local)"
  npm install
else
  echo "No package.json found. Running npm init and installing mapshaper"
  npm init -y
  npm install --save mapshaper
fi

echo "making other shell scripts executable"
chmod +x simplify_geojson.sh run_scripts.sh

echo "Setup complete. Activate the venv with: source $VENV_DIR/bin/activate"
