# GitHub Sync Quick Start Guide

## Current Status

✅ **obsidian-vault folder**: Ready for GitHub Sync  
✅ **Git repository**: Initialized  
✅ **Files committed**: All reports are tracked  
✅ **Main repo**: Updated to ignore obsidian-vault

## Setup the GitHub Sync Plugin

### Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `hedge-fund-research-notes` (or your choice)
3. Set to **Private** (recommended for research notes)
4. **Don't** initialize with README, .gitignore, or license
5. Click **Create repository**

### Step 2: Connect obsidian-vault to GitHub

**Copy the commands from GitHub** (they'll show after creating the repo), or use:

```bash
cd /Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research/obsidian-vault

# Add remote (replace YOUR_USERNAME and REPO_NAME)
git remote add origin https://github.com/YOUR_USERNAME/hedge-fund-research-notes.git

# Or if using SSH:
# git remote add origin git@github.com:YOUR_USERNAME/hedge-fund-research-notes.git

# Push to GitHub
git branch -M main
git push -u origin main
```

### Step 3: Install GitHub Sync Plugin in Obsidian

1. Open **Obsidian app**
2. Go to **Settings** → **Community plugins**
3. Click **Browse**
4. Search for **"GitHub Sync"**
5. Install plugin by **kevinmkchin**
6. **Enable** the plugin

### Step 4: Configure Plugin

1. In Obsidian settings, find **GitHub Sync**
2. Enter **Remote URL**:
   - `https://github.com/YOUR_USERNAME/hedge-fund-research-notes.git`
   - Or SSH: `git@github.com:YOUR_USERNAME/hedge-fund-research-notes.git`
3. Save settings

### Step 5: Open Vault in Obsidian

1. In Obsidian, click **Open another vault**
2. Select **Open folder as vault**
3. Navigate to: `hedge-fund-research/obsidian-vault/`
4. Open it

### Step 6: Test Sync

1. Click the **Sync with Remote** ribbon icon (or use Command Palette)
2. First sync will push your files to GitHub
3. Verify on GitHub that files appear

## How It Works

```
System generates report → Saves to obsidian-vault/ → GitHub Sync plugin → Pushes to GitHub
```

## Current Files Ready to Sync

- `_Index.md` - Project overview (4.9KB)
- `Daily-Notes/2026-01-25.md` - Daily note
- `.gitignore` - Git ignore rules

## Benefits

✅ **No iCloud permission issues** - Direct git operations  
✅ **Version control** - Full history of all changes  
✅ **Cross-device sync** - Pull on any device  
✅ **Backup** - Automatic backup to GitHub  
✅ **Free** - Private repos are free

## Usage After Setup

1. **Generate reports**: `python scripts/generate_obsidian_report.py --type daily`
2. **Reports save to**: `obsidian-vault/` (automatically)
3. **Sync in Obsidian**: Click "Sync with Remote" button
4. **Access elsewhere**: Pull from GitHub on other devices

## Troubleshooting

### Authentication
- **HTTPS**: Create Personal Access Token (GitHub Settings → Developer settings)
- **SSH**: Ensure SSH key is added to GitHub

### Git Not Found
- Set custom git path in plugin settings if git is not in PATH

### First Push
- May need to authenticate with GitHub credentials
- Use Personal Access Token for HTTPS (not password)
