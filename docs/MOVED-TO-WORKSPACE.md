# Project Moved to Workspace

## New Location

The `hedge-fund-research` project has been moved to:
```
/Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research
```

## What Was Updated

✅ **Configuration files** - All paths are relative or use `Path(__file__).parent`, so they automatically work in the new location

✅ **Documentation** - Updated all documentation files that referenced the old path:
- `docs/MACOS-PERMISSIONS.md`
- `docs/GOOGLE-DRIVE-SETUP.md`
- `docs/GITHUB-SYNC-MANUAL-SETUP.md`
- `docs/GITHUB-SYNC-QUICK-START.md`
- `docs/GITHUB-SYNC-READY.md`
- `docs/OBSIDIAN-GITHUB-SYNC-SETUP.md`
- `docs/ICLOUD-SYNC-SETUP.md`

✅ **Config.py** - Updated to handle empty `OBSIDIAN_PROJECT_FOLDER` correctly (saves to vault root when empty)

## Current Configuration

The `.env` file is configured for:
- **Data Storage**: `/Volumes/Data_2026/hedge-fund-research-data` (external drive)
- **Obsidian Vault**: `~/Documents/google_drive/hedge-fund-research-obsidian` (Google Drive sync)
- **Project Folder**: Empty (saves directly to vault root)

## Testing

To verify everything works:

```bash
cd /Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research
source .venv/bin/activate
python scripts/test_obsidian_path.py
```

## Notes

- The virtual environment (`.venv`) is in the project directory and should work as-is
- All relative paths in the codebase will automatically work in the new location
- The `.env` file paths are absolute or use `~`, so they don't need updating
