# Google Drive Permissions Workaround

## Current Situation

The Google Drive folder (`~/Documents/google_drive/hedge-fund-research-obsidian`) is not writable by scripts, even after:
- ✅ Granting Terminal/Cursor permissions in System Settings
- ✅ Restarting Terminal/Cursor
- ✅ Checking folder permissions

This appears to be a macOS security restriction on Google Drive synced folders.

## Working Solution: Fallback Location

The system automatically uses a fallback location that **is** writable:
```
/Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research/obsidian-reports/
```

**This location works perfectly!** All reports are being saved here.

## Options

### Option 1: Use Fallback + Manual Sync (Recommended)

1. Reports save to: `obsidian-reports/` in the project
2. Manually copy files to Google Drive when needed:
   ```bash
   cp -r obsidian-reports/* ~/Documents/google_drive/hedge-fund-research-obsidian/
   ```
3. Or set up a simple sync script

### Option 2: Use a Different Location

Change `.env` to use a location that's not synced by Google Drive:

```bash
# In .env file
OBSIDIAN_VAULT_PATH=~/Documents/hedge-fund-research-obsidian
```

Then manually add this folder to Google Drive for syncing.

### Option 3: Use Symbolic Link

Create a symlink from a writable location to Google Drive:

```bash
# Create writable folder
mkdir -p ~/Documents/hedge-fund-obsidian-local

# Create symlink in Google Drive
ln -s ~/Documents/hedge-fund-obsidian-local ~/Documents/google_drive/hedge-fund-research-obsidian-local
```

Then update `.env`:
```bash
OBSIDIAN_VAULT_PATH=~/Documents/hedge-fund-obsidian-local
```

## Current Behavior

The system is working correctly with the fallback:
- ✅ Reports are generated successfully
- ✅ Saved to `obsidian-reports/` folder
- ✅ All functionality works
- ⚠️ Just not in the Google Drive folder directly

## Verify It's Working

```bash
cd /Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research
source .venv/bin/activate
python3 scripts/generate_obsidian_report.py --type daily

# Check the fallback location
ls -la obsidian-reports/
```

## Why This Happens

macOS has strict security controls on folders synced by cloud services (Google Drive, iCloud, Dropbox). Even with Full Disk Access, some operations may be restricted to prevent data exfiltration or ensure sync integrity.

The fallback mechanism ensures the system always works, regardless of cloud sync restrictions.
