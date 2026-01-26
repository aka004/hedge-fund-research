#!/usr/bin/env python3
"""Interactive configuration setup for hedge-fund-research.

Helps configure data storage and Obsidian vault paths.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    OBSIDIAN_PROJECT_PATH,
    OBSIDIAN_VAULT_PATH,
    STORAGE_PATH,
    get_storage_path,
    get_obsidian_vault_path,
)


def print_current_config():
    """Print current configuration."""
    print("\n" + "=" * 60)
    print("CURRENT CONFIGURATION")
    print("=" * 60)
    print(f"Data Storage Path: {STORAGE_PATH}")
    print(f"  Exists: {STORAGE_PATH.exists()}")
    if STORAGE_PATH.exists():
        try:
            size = sum(f.stat().st_size for f in STORAGE_PATH.rglob('*') if f.is_file())
            print(f"  Size: {size / (1024*1024):.1f} MB")
        except:
            pass
    
    print(f"\nObsidian Vault Path: {OBSIDIAN_VAULT_PATH}")
    print(f"  Exists: {OBSIDIAN_VAULT_PATH.exists()}")
    
    print(f"\nObsidian Project Path: {OBSIDIAN_PROJECT_PATH}")
    print(f"  Exists: {OBSIDIAN_PROJECT_PATH.exists()}")
    print("=" * 60 + "\n")


def check_external_drives():
    """Check for available external drives."""
    drives = []
    volumes = Path("/Volumes")
    if volumes.exists():
        for vol in volumes.iterdir():
            if vol.is_dir() and not vol.name.startswith('.'):
                try:
                    stat = vol.stat()
                    drives.append(str(vol))
                except:
                    pass
    return drives


def main():
    """Main setup function."""
    print("\n" + "=" * 60)
    print("Hedge Fund Research - Configuration Setup")
    print("=" * 60)
    
    print_current_config()
    
    # Check external drives
    drives = check_external_drives()
    if drives:
        print("Available External Drives:")
        for drive in drives:
            print(f"  - {drive}")
        print()
    
    print("Configuration is ready!")
    print("\nTo change settings, edit the .env file:")
    print("  - DATA_STORAGE_PATH: Set to external drive path if desired")
    print("  - OBSIDIAN_VAULT_PATH: Set to your Obsidian vault location")
    print("\nThe Obsidian project folder will be created automatically")
    print("when you generate your first report.\n")


if __name__ == "__main__":
    main()
