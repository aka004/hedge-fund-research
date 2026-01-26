# Where Are My Notes?

## Current Location

Your notes are currently saved in:
```
/Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research/obsidian-reports/
```

**Files found:**
- `_Index.md` - Project overview
- `Daily-Notes/2026-01-25.md` - Daily note

## Why They're Not in Google Drive

Due to macOS security restrictions, the system cannot write directly to the Google Drive folder. It automatically saves to a fallback location that **is** writable.

## How to Get Them to Google Drive

### Option 1: Manual Copy (Easiest)

1. **Open Finder**
2. Navigate to:
   ```
   /Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research/obsidian-reports/
   ```
3. **Select all files** (Cmd+A)
4. **Copy** (Cmd+C)
5. Navigate to:
   ```
   ~/Documents/google_drive/hedge-fund-research-obsidian
   ```
6. **Paste** (Cmd+V)

The files will then sync to Google Drive automatically!

### Option 2: Use Terminal (If Permissions Allow)

```bash
# Try copying (may fail due to permissions)
cp -r /Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research/obsidian-reports/* ~/Documents/google_drive/hedge-fund-research-obsidian/
```

If this fails, use Option 1 (Finder).

### Option 3: Change Configuration

If you want future notes to go directly to Google Drive (once permissions are fixed), the system is already configured for that. The notes will automatically save there once write access is available.

## Quick Access

I've opened both folders in Finder for you:
- **Source folder** (where notes are now)
- **Target folder** (where you want them in Google Drive)

Just drag and drop the files!

## Verify After Copying

After copying, check Google Drive:
```bash
find ~/Documents/google_drive/hedge-fund-research-obsidian -name "*.md"
```

You should see:
- `_Index.md`
- `Daily-Notes/2026-01-25.md`
