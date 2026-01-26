# Configuration Guide

## Quick Setup

### 1. Data Storage Path

You have several options for data storage:

**Option A: Keep data in project directory (default)**
- No configuration needed
- Data stored at: `./data/cache`
- Good for: Small datasets, development

**Option B: Use external drive (recommended for large datasets)**
- Available drives:
  - `/Volumes/Drive 2025` (347GB free) - **Recommended**
  - `/Volumes/Untitled` (466GB free)

To configure, edit `.env`:
```bash
DATA_STORAGE_PATH=/Volumes/Drive 2025/hedge-fund-research-data
```

Then create the directory:
```bash
mkdir -p "/Volumes/Drive 2025/hedge-fund-research-data"
```

### 2. Obsidian Vault Path

**Find your Obsidian vault:**
1. Open Obsidian app
2. Go to Settings → About → Vault location
3. Copy the path

**Or check common locations:**
```bash
# Check if vault exists
ls ~/Documents/Obsidian
ls ~/Documents/Obsidian/Projects
```

**To configure, edit `.env`:**
```bash
OBSIDIAN_VAULT_PATH=/path/to/your/obsidian/vault
```

**If vault doesn't exist yet:**
The system will create the project folder automatically when you generate your first report.

## Current Configuration

Check your current settings:
```bash
python3 -c "from config import STORAGE_PATH, OBSIDIAN_PROJECT_PATH; print(f'Storage: {STORAGE_PATH}'); print(f'Obsidian: {OBSIDIAN_PROJECT_PATH}')"
```

## Migration

If you want to move existing data to external drive:

1. **Set new path in `.env`:**
   ```bash
   DATA_STORAGE_PATH=/Volumes/Drive 2025/hedge-fund-research-data
   ```

2. **Create directory:**
   ```bash
   mkdir -p "/Volumes/Drive 2025/hedge-fund-research-data"
   ```

3. **Copy existing data (optional):**
   ```bash
   cp -r data/cache/* "/Volumes/Drive 2025/hedge-fund-research-data/"
   ```

4. **Verify:**
   ```bash
   python scripts/fetch_data.py --status
   ```

## Testing Configuration

Test that everything works:
```bash
# Test config loading
python3 -c "from config import *; print('Config loaded successfully')"

# Test Obsidian report generation (creates vault structure if needed)
python scripts/generate_obsidian_report.py --type daily
```
