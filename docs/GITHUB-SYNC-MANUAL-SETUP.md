# GitHub Sync Manual Setup Instructions

## Current Situation

The `obsidian-vault` folder is currently part of the parent git repository. For the GitHub Sync plugin to work, it needs to be a **separate, independent git repository**.

## Why This Is Needed

The [Obsidian GitHub Sync plugin](https://github.com/kevinmkchin/Obsidian-GitHub-Sync) expects the Obsidian vault itself to be a git repository that it can sync to GitHub. Since `obsidian-vault` is currently tracked by the parent repo, we need to make it independent.

## Manual Setup Steps

### Step 1: Remove from Parent Repo (Already Done)

✅ The main `.gitignore` has been updated to exclude `obsidian-vault/`

### Step 2: Create Separate Git Repository

**Option A: Using Terminal (Recommended)**

```bash
cd /Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research/obsidian-vault

# Remove any existing .git if it's linked to parent
rm -rf .git

# Initialize new git repository
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: Hedge Fund Research Obsidian notes"
```

**Option B: Using Obsidian GitHub Sync Plugin**

The plugin can initialize git for you:
1. Install the plugin in Obsidian
2. Open the vault in Obsidian
3. Configure the remote URL
4. Plugin will handle git operations

### Step 3: Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `hedge-fund-research-notes` (or your choice)
3. Set to **Private**
4. **Don't** initialize with any files
5. Click **Create repository**

### Step 4: Connect to GitHub

```bash
cd /Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research/obsidian-vault

# Add remote (replace YOUR_USERNAME and REPO_NAME)
git remote add origin https://github.com/YOUR_USERNAME/hedge-fund-research-notes.git

# Push to GitHub
git branch -M main
git push -u origin main
```

### Step 5: Configure GitHub Sync Plugin

1. **Install Plugin** in Obsidian:
   - Settings → Community plugins → Browse
   - Search "GitHub Sync" by kevinmkchin
   - Install and enable

2. **Configure Remote URL**:
   - Settings → GitHub Sync
   - Remote URL: `https://github.com/YOUR_USERNAME/hedge-fund-research-notes.git`
   - Save

3. **Open Vault**:
   - Open folder as vault: `hedge-fund-research/obsidian-vault/`

4. **Test Sync**:
   - Click "Sync with Remote" ribbon icon
   - Files should push to GitHub

## Current Files Ready

- ✅ `_Index.md` - Project overview (4.9KB)
- ✅ `Daily-Notes/2026-01-25.md` - Daily note
- ✅ `.gitignore` - Git ignore rules

## Verification

After setup, verify:

```bash
cd /Users/yung004/Documents/claude_code/claude-code-workspace/hedge-fund-research/obsidian-vault
git remote -v  # Should show your GitHub repo
git status     # Should show clean or your changes
```

## How It Works After Setup

1. **System generates report** → Saves to `obsidian-vault/`
2. **You click "Sync with Remote"** in Obsidian → Pushes to GitHub
3. **Access on other devices** → Pull from GitHub

## Benefits

✅ **No permission issues** - Direct git operations  
✅ **Version control** - Full history of changes  
✅ **Cross-device** - Works on all platforms  
✅ **Backup** - Automatic backup to GitHub  
✅ **Free** - Private repos are free

## Troubleshooting

### Permission Errors
If you get permission errors, you may need to:
- Run commands from Terminal (not through scripts)
- Check folder permissions: `ls -ld obsidian-vault`

### Git Already Initialized
If git is already initialized but linked to parent:
```bash
cd obsidian-vault
rm -rf .git
git init
git add .
git commit -m "Initial commit"
```

### Authentication
- **HTTPS**: Use Personal Access Token (GitHub Settings → Developer settings)
- **SSH**: Ensure SSH key is added to GitHub
