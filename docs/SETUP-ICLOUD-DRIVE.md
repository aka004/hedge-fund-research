# Setup Guide: iCloud Drive Obsidian + External Drive Data

## Configuration Summary

✅ **Obsidian Vault**: iCloud Drive (`/Users/yung004/Library/Mobile Documents/iCloud~md~obsidian`)  
✅ **Data Storage**: External Drive (`/Volumes/Drive 2025/Finance:coding/hedge-fund-research-data`)

## Manual Setup Steps

### 1. Create Data Storage Folder on External Drive

Due to permission restrictions, you'll need to create the data folder manually:

**Option A: Using Finder**
1. Open Finder
2. Navigate to "Drive 2025" → "Finance:coding"
3. Create a new folder named `hedge-fund-research-data`
4. The full path should be: `/Volumes/Drive 2025/Finance:coding/hedge-fund-research-data`

**Option B: Using Terminal (if you have permissions)**
```bash
mkdir -p "/Volumes/Drive 2025/Finance:coding/hedge-fund-research-data"
```

**Option C: Use a Different Location**
If you can't create folders in "Finance:coding", you can:
- Use an existing writable folder on Drive 2025
- Or keep data in project directory (default: `./data/cache`)

To change the location, edit `.env`:
```bash
DATA_STORAGE_PATH=/path/to/your/chosen/location
```

### 2. Verify Obsidian Vault Structure

The Obsidian vault is configured to use:
- **Vault Root**: `/Users/yung004/Library/Mobile Documents/iCloud~md~obsidian`
- **Project Folder**: `Projects/hedge-fund-research/`

The system will automatically create the `Projects/hedge-fund-research/` folder structure when you generate your first report.

### 3. Test Configuration

After creating the data folder, test the setup:

```bash
# Activate virtual environment
source venv/bin/activate

# Check configuration
python scripts/setup_config.py

# Test data storage
python -c "from config import STORAGE_PATH; from data.storage.parquet import ParquetStorage; storage = ParquetStorage(STORAGE_PATH); print(f'Storage path: {STORAGE_PATH}')"

# Test Obsidian report generation
python scripts/generate_obsidian_report.py --type daily
```

## Current Configuration

Your `.env` file is configured with:

```bash
# Data storage on external drive
DATA_STORAGE_PATH=/Volumes/Drive 2025/Finance:coding/hedge-fund-research-data

# Obsidian vault in iCloud Drive
OBSIDIAN_VAULT_PATH=/Users/yung004/Library/Mobile Documents/iCloud~md~obsidian
OBSIDIAN_PROJECT_FOLDER=Projects/hedge-fund-research
```

## Troubleshooting

### If Data Folder Creation Fails

1. **Check drive permissions**: Make sure "Drive 2025" is mounted and you have write access
2. **Try a different location**: Use an existing folder you know you can write to
3. **Use project directory**: Leave `DATA_STORAGE_PATH` empty to use `./data/cache`

### If Obsidian Reports Don't Save

1. **Check iCloud sync**: Make sure iCloud Drive is syncing properly
2. **Check vault location**: Verify the vault path in Obsidian app settings
3. **Fallback location**: Reports will save to `obsidian-reports/` in project directory if vault is inaccessible

## Migration from Current Data

If you have existing data in `./data/cache` and want to move it:

```bash
# After creating the new data folder
cp -r data/cache/* "/Volumes/Drive 2025/Finance:coding/hedge-fund-research-data/"
```

## Benefits of This Setup

✅ **iCloud Obsidian Vault**: 
- Syncs across all your devices
- Accessible from iPhone/iPad Obsidian app
- Automatic cloud backup

✅ **External Drive Data Storage**:
- Keeps large datasets off your main drive
- 347GB available on Drive 2025
- Faster access for large data operations
