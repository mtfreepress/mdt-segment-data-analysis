#!/usr/bin/env bash
set -euo pipefail

# Run the Python merge script, then the mapshaper simplifier
VENV_DIR=".venv"

if [ -d "$VENV_DIR" ]; then
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
else
  echo "Virtual environment not found at $VENV_DIR. Run ./setup.sh first or set PYTHON env to create one." >&2
  exit 1
fi

python merge_traffic_accident.py

# Now run the simplifier script (uses local node_modules mapshaper if available)
./simplify_geojson.sh

echo "Pipeline complete: merged data generated and simplified files are in simplified_data/"