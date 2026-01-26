#!/bin/bash
# Setup script for hedge-fund-research environment
# Run this when you have internet connection

set -e

echo "=========================================="
echo "Hedge Fund Research - Environment Setup"
echo "=========================================="
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "📍 Project root: $PROJECT_ROOT"
echo ""

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "   Creating new virtual environment..."
    python3 -m venv .venv
    echo "✅ Virtual environment created"
fi

# Activate venv
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📦 Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo ""
echo "✅ Dependencies installed!"
echo ""

# Verify installation
echo "🔍 Verifying installation..."
python3 -c "import pandas, numpy; from dotenv import load_dotenv; print('✅ Core dependencies: pandas, numpy, python-dotenv')" || {
    echo "❌ Verification failed"
    exit 1
}

# Test configuration
echo "🔍 Testing configuration..."
python3 -c "
import sys
sys.path.insert(0, '.')
from config import OBSIDIAN_PROJECT_PATH, OBSIDIAN_VAULT_PATH, STORAGE_PATH
print('✅ Configuration loaded:')
print(f'   Data Storage: {STORAGE_PATH}')
print(f'   Obsidian Vault: {OBSIDIAN_VAULT_PATH}')
print(f'   Project Path: {OBSIDIAN_PROJECT_PATH}')
"

echo ""
echo "=========================================="
echo "✅ Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Activate the environment: source .venv/bin/activate"
echo "2. Test Obsidian path: python scripts/test_obsidian_path.py"
echo "3. Generate a report: python scripts/generate_obsidian_report.py --type daily"
echo ""
