#!/bin/bash
# Sync obsidian-reports to Google Drive folder
# Run this manually when you want to sync reports to Google Drive

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SOURCE_DIR="$PROJECT_ROOT/obsidian-reports"
TARGET_DIR="$HOME/Documents/google_drive/hedge-fund-research-obsidian"

echo "=========================================="
echo "Syncing Obsidian Reports to Google Drive"
echo "=========================================="
echo ""
echo "Source: $SOURCE_DIR"
echo "Target: $TARGET_DIR"
echo ""

if [ ! -d "$SOURCE_DIR" ]; then
    echo "❌ Source directory not found: $SOURCE_DIR"
    exit 1
fi

# Check if target exists (even if not writable)
if [ ! -d "$TARGET_DIR" ]; then
    echo "⚠️  Target directory not found: $TARGET_DIR"
    echo "   Creating it..."
    mkdir -p "$TARGET_DIR" || {
        echo "❌ Cannot create target directory"
        echo "   You may need to create it manually in Finder"
        exit 1
    }
fi

# Try to copy files
echo "📋 Copying files..."
if cp -r "$SOURCE_DIR"/* "$TARGET_DIR"/ 2>/dev/null; then
    echo "✅ Files copied successfully!"
    echo ""
    echo "Files synced:"
    find "$TARGET_DIR" -type f -name "*.md" | wc -l | xargs echo "   Markdown files:"
else
    echo "❌ Copy failed - permission denied"
    echo ""
    echo "Workaround:"
    echo "1. Open Finder"
    echo "2. Navigate to: $SOURCE_DIR"
    echo "3. Manually copy files to: $TARGET_DIR"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ Sync complete!"
echo "=========================================="
