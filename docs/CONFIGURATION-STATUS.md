# Configuration Status

## ✅ Configured Paths

### Obsidian Vault (iCloud Drive)
- **Vault Location**: `/Users/yung004/Library/Mobile Documents/iCloud~md~obsidian`
- **Project Folder**: `Documents/hedge-fund-research/`
- **Full Path**: `iCloud~md~obsidian/Documents/hedge-fund-research/`
- **Status**: ⚠️ May need manual folder creation in Obsidian app

### Data Storage (External Drive)
- **Location**: `/Volumes/Drive 2025/Finance:coding/hedge-fund-research-data`
- **Status**: ⚠️ Needs manual folder creation (permission restrictions)

## Setup Instructions

### Step 1: Create Data Folder on External Drive

**Using Finder:**
1. Open Finder
2. Go to "Drive 2025" → "Finance:coding"
3. Right-click → New Folder
4. Name it: `hedge-fund-research-data`

**Alternative:** If you can't create in "Finance:coding", use any writable folder on Drive 2025 and update `.env`:
```bash
DATA_STORAGE_PATH=/Volumes/Drive 2025/your-folder/hedge-fund-research-data
```

### Step 2: Set Up Obsidian Project Folder

**Option A: Create in Obsidian App (Recommended)**
1. Open Obsidian app
2. Navigate to your vault
3. Create folder: `Documents/hedge-fund-research/`
4. Or create `Projects/hedge-fund-research/` if you prefer

**Option B: Create via Finder**
1. Navigate to: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/`
2. Create folder: `hedge-fund-research`

**Option C: Use Existing Documents Folder**
The system is configured to use `Documents/hedge-fund-research/` which will be created automatically when possible.

### Step 3: Verify Configuration

```bash
source venv/bin/activate
python scripts/setup_config.py
```

## Current Behavior

- **Obsidian Reports**: Will save to iCloud vault when folder exists, otherwise falls back to `obsidian-reports/` in project directory
- **Data Storage**: Will use external drive path when folder exists, otherwise uses `./data/cache` (current location)

## Testing

After creating the folders, test with:

```bash
# Test Obsidian report
python scripts/generate_obsidian_report.py --type daily

# Test data storage
python -c "from config import STORAGE_PATH; print(f'Using: {STORAGE_PATH}')"
```

## Benefits

✅ **iCloud Obsidian**: Syncs across devices, accessible from mobile  
✅ **External Drive Data**: Keeps 41MB+ (and growing) data off main drive  
✅ **Automatic Fallback**: System works even if folders don't exist yet
