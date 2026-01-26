#!/usr/bin/env python3
"""Test Obsidian path configuration and folder access."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OBSIDIAN_PROJECT_PATH
import os

def test_obsidian_path():
    """Test if Obsidian path is accessible."""
    print(f"\n{'='*60}")
    print("Obsidian Path Test")
    print(f"{'='*60}\n")
    
    print(f"Configured Path: {OBSIDIAN_PROJECT_PATH}")
    print(f"Exists: {OBSIDIAN_PROJECT_PATH.exists()}")
    
    if OBSIDIAN_PROJECT_PATH.exists():
        print(f"Writable: {os.access(OBSIDIAN_PROJECT_PATH, os.W_OK)}")
        
        # Test write
        test_file = OBSIDIAN_PROJECT_PATH / ".test_write"
        try:
            test_file.write_text("test")
            test_file.unlink()
            print("✅ Write test: SUCCESS")
            print("\n✅ Folder is ready! Reports will save here.")
        except Exception as e:
            print(f"❌ Write test: FAILED - {e}")
    else:
        print(f"\n⏳ Folder doesn't exist yet.")
        print(f"Please create: {OBSIDIAN_PROJECT_PATH}")
        print(f"\nUsing Finder or Terminal:")
        print(f"  mkdir -p {OBSIDIAN_PROJECT_PATH}")
    
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    test_obsidian_path()
