#!/bin/bash
# Activation script for hedge-fund-research virtual environment
# Usage: source activate.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${SCRIPT_DIR}/venv"

if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment not found at: $VENV_PATH"
    echo "   Run: python3 -m venv venv"
    echo "   Then: pip install -r requirements.txt"
    return 1 2>/dev/null || exit 1
fi

# Activate the virtual environment
source "${VENV_PATH}/bin/activate"

# Verify activation
if [ -n "$VIRTUAL_ENV" ]; then
    echo "✓ Virtual environment activated: $VIRTUAL_ENV"
    echo "✓ Python: $(which python3)"
    echo "✓ Python version: $(python3 --version)"
    echo ""
    echo "Available commands:"
    echo "  python3 -m pytest tests/     # Run tests"
    echo "  jupyter lab                  # Start Jupyter Lab"
    echo "  python3 scripts/fetch_data.py # Fetch market data"
    echo ""
else
    echo "❌ Failed to activate virtual environment"
    return 1 2>/dev/null || exit 1
fi
