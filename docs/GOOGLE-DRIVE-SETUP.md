# Google Drive Setup

## Configuration Complete ✅

The system is now configured to save Obsidian reports to:
- **Path**: `~/Documents/google_drive/hedge-fund-research-obsidian/`
- **Full Path**: `/Users/yung004/Documents/google_drive/hedge-fund-research-obsidian/`

## Manual Folder Creation

Since Google Drive folders may have permission restrictions, create the folder manually:

### Option 1: Using Finder
1. Open Finder
2. Navigate to: `Documents/google_drive/`
3. Create new folder: `hedge-fund-research-obsidian`
4. The folder will sync to Google Drive automatically

### Option 2: Using Terminal
```bash
mkdir -p ~/Documents/google_drive/hedge-fund-research-obsidian
```

## Verify Setup

After creating the folder, test it:

```bash
cd /Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research
source venv/bin/activate

# Test report generation
python scripts/generate_obsidian_report.py --type daily

# Check if file was created
ls -la ~/Documents/google_drive/hedge-fund-research-obsidian/
```

## How It Works

1. **System generates report** → Saves to `~/Documents/google_drive/hedge-fund-research-obsidian/`
2. **Google Drive syncs** → Files automatically sync to Google Drive
3. **Access anywhere** → Files available on all devices via Google Drive

## Folder Structure

```
~/Documents/google_drive/hedge-fund-research-obsidian/
├── _Index.md                    # Project overview
├── Research/
│   ├── Alpha-Research/          # Research summaries
│   └── Backtests/              # Backtest reports
└── Daily-Notes/                # Daily notes
```

## Benefits

✅ **Direct Write Access**: Scripts can write directly (no permission issues once folder exists)  
✅ **Google Drive Sync**: Automatic syncing to Google Drive  
✅ **Cross-Device Access**: Access reports on any device  
✅ **Backup**: Automatic backup to Google Drive cloud  
✅ **Obsidian Compatible**: Can open folder as vault in Obsidian

## Using with Obsidian

1. Open Obsidian app
2. Click **Open another vault** → **Open folder as vault**
3. Select: `~/Documents/google_drive/hedge-fund-research-obsidian/`
4. All reports will appear in Obsidian
5. Changes sync via Google Drive

## Current Configuration

```bash
# In .env file
OBSIDIAN_VAULT_PATH=~/Documents/google_drive/hedge-fund-research-obsidian
OBSIDIAN_PROJECT_FOLDER=
```

## Migration from Old Location

If you have files in the old `obsidian-vault/` folder:

```bash
# Copy files to new location (after creating folder)
cp -r obsidian-vault/* ~/Documents/google_drive/hedge-fund-research-obsidian/
```
