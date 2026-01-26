# macOS Permission Issues

## Problem

If you see errors like:
```
PermissionError: [Errno 1] Operation not permitted
```

When trying to save Obsidian reports to `~/Documents/google_drive/hedge-fund-research-obsidian`, this is a macOS security restriction.

## Why This Happens

macOS requires explicit permission for scripts and applications to write to certain folders, especially:
- Folders synced by cloud services (Google Drive, iCloud, Dropbox)
- Folders in `Documents` that have special attributes
- Folders with extended attributes (indicated by `@` in `ls -la` output)

## Solution

### Option 1: Grant Files and Folders Permission (Recommended)

1. Open **System Settings** (or System Preferences on older macOS)
2. Go to **Privacy & Security** > **Files and Folders**
3. Find **Terminal** (or **Cursor** if it appears)
4. Enable access to:
   - **Documents Folder**
   - Or **Full Disk Access** (more permissive)

### Option 2: Grant Full Disk Access

1. Open **System Settings** > **Privacy & Security** > **Full Disk Access**
2. Click the **+** button
3. Add **Terminal** (or **Cursor** if available)
4. Restart Terminal/Cursor

### Option 3: Use a Different Location

If you can't grant permissions, you can:
1. Use a location outside `Documents` (e.g., `~/hedge-fund-research-obsidian`)
2. Manually sync that folder to Google Drive using Finder
3. Update `.env` with the new path

## Verify Permissions

After granting permissions, test with:
```bash
python scripts/test_obsidian_path.py
```

## Current Behavior

The system will automatically fallback to saving reports in:
```
/Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research/obsidian-reports/
```

You can manually copy these files to your Google Drive folder, or grant permissions to enable automatic saving.
