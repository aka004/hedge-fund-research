# Environment Setup Guide

## Quick Setup

When you have internet connection, run:

```bash
cd /Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research
./scripts/setup_environment.sh
```

This will:
1. ✅ Activate/create virtual environment
2. ✅ Upgrade pip
3. ✅ Install all dependencies from `requirements.txt`
4. ✅ Verify installation
5. ✅ Test configuration

## Manual Setup

If the script doesn't work, do it manually:

```bash
# Navigate to project
cd /Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Verify
python3 -c "import pandas, numpy; from dotenv import load_dotenv; print('✅ OK')"
```

## Current .env Configuration

Your `.env` file is configured with:

```bash
# Data storage (external drive)
DATA_STORAGE_PATH=/Volumes/Data_2026/hedge-fund-research-data

# Obsidian vault (Google Drive sync)
OBSIDIAN_VAULT_PATH=~/Documents/google_drive/hedge-fund-research-obsidian
OBSIDIAN_PROJECT_FOLDER=

# Logging
LOG_LEVEL=INFO
```

## Verify Configuration

After installing dependencies, test the configuration:

```bash
source .venv/bin/activate
python3 -c "
import sys
sys.path.insert(0, '.')
from config import OBSIDIAN_PROJECT_PATH, OBSIDIAN_VAULT_PATH, STORAGE_PATH
print('Data Storage:', STORAGE_PATH)
print('Obsidian Vault:', OBSIDIAN_VAULT_PATH)
print('Project Path:', OBSIDIAN_PROJECT_PATH)
"
```

Expected output:
- **Data Storage**: `/Volumes/Data_2026/hedge-fund-research-data`
- **Obsidian Vault**: `/Users/yung004/Documents/google_drive/hedge-fund-research-obsidian`
- **Project Path**: `/Users/yung004/Documents/google_drive/hedge-fund-research-obsidian`

## Test Obsidian Sync

Once dependencies are installed and permissions are set:

```bash
source .venv/bin/activate
python3 scripts/test_obsidian_path.py
python3 scripts/generate_obsidian_report.py --type daily
```

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'dotenv'"
**Solution**: Run `pip install python-dotenv` or run the setup script

### Issue: Configuration shows default paths instead of .env values
**Solution**: Make sure `python-dotenv` is installed. The config.py will fall back to defaults if dotenv isn't available.

### Issue: Permission errors when writing to Google Drive folder
**Solution**: 
1. System Settings → Privacy & Security → Files and Folders
2. Enable "Documents Folder" or "Full Disk Access" for Terminal/Cursor
3. **Restart Terminal/Cursor** after granting permissions

### Issue: No internet connection
**Solution**: Wait until you have internet, then run the setup script. The script will install all dependencies automatically.
