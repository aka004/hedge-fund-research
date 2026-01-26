# iCloud Drive Sync Setup for Obsidian Reports

## Current Configuration

Reports are now saved to a **local folder** in your project that you can sync to iCloud Drive:
- **Local Path**: `hedge-fund-research/obsidian-vault/`
- **Full Path**: `/Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research/obsidian-vault/`
- **Status**: ✅ Working - scripts can write directly!

## Benefits

✅ **Direct Write Access**: Scripts can write directly (no permission issues)  
✅ **iCloud Sync**: Add folder to iCloud Drive for syncing  
✅ **Obsidian Access**: Configure Obsidian to watch this folder  
✅ **Flexible**: Can be accessed locally or synced to cloud

## Setup Options

### Option 1: Add Folder to iCloud Drive (Recommended)

1. **Open Finder**
2. Navigate to your project: `hedge-fund-research/`
3. **Right-click** the `obsidian-vault` folder
4. **Drag it** to iCloud Drive in Finder sidebar, OR
5. **Right-click** → **Share** → **Add to iCloud Drive**
6. The folder will sync to iCloud and be accessible on all devices

**Alternative**: Create a symbolic link in iCloud Drive:
```bash
cd "/Users/yung004/Library/Mobile Documents/iCloud~md~obsidian/Documents"
ln -s "/Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research/obsidian-vault" hedge-fund-research
```

### Option 2: Configure Obsidian to Watch Local Folder

1. **Open Obsidian app**
2. Click **Open another vault** (or **File** → **Open Vault**)
3. Click **Open folder as vault**
4. Navigate to and select: `hedge-fund-research/obsidian-vault/`
5. Obsidian will watch this folder for changes
6. All reports will appear automatically in Obsidian

### Option 3: Use Symbolic Link (Advanced)

If you want reports in a specific iCloud location:

```bash
# Create symlink from iCloud to local folder
ln -s ~/Documents/hedge-fund-research-obsidian \
  "/Users/yung004/Library/Mobile Documents/iCloud~md~obsidian/Documents/hedge-fund-research"
```

## Current Setup

The system is configured to save reports to:
```
~/Documents/hedge-fund-research-obsidian/
├── _Index.md                    # Project overview (already created)
├── Research/
│   ├── Alpha-Research/          # Research summaries
│   └── Backtests/              # Backtest reports
└── Daily-Notes/                # Daily notes
```

## Testing

Test that reports are saving correctly:

```bash
# Generate a test report
python scripts/generate_obsidian_report.py --type daily

# Check if file was created
ls -la obsidian-vault/
```

After adding to iCloud Drive, the files will sync automatically.

The file should appear in:
- Local folder: `~/Documents/hedge-fund-research-obsidian/`
- iCloud Drive: (after syncing)
- Obsidian app: (if configured to watch the folder)

## Changing the Location

To use a different local folder, edit `.env`:

```bash
OBSIDIAN_VAULT_PATH=/path/to/your/local/folder
```

Then add that folder to iCloud Drive using the same method above.
