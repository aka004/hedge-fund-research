"""Centralized configuration for hedge-fund-research project.

Reads configuration from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    # Load .env file if it exists
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # dotenv not installed, manually load .env file
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

# Project root directory
PROJECT_ROOT = Path(__file__).parent


def get_storage_path() -> Path:
    """Get the data storage path.
    
    Reads from DATA_STORAGE_PATH environment variable, or defaults to
    project_root/data/cache if not set.
    
    Returns:
        Path to data storage directory
    """
    env_path = os.getenv("DATA_STORAGE_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    
    # Default to project-relative path
    return PROJECT_ROOT / "data" / "cache"


def get_obsidian_vault_path() -> Path:
    """Get the Obsidian vault path.
    
    Reads from OBSIDIAN_VAULT_PATH environment variable.
    If set to a local path, that will be used (can be synced to iCloud).
    If not set, defaults to project directory that can be synced.
    
    Returns:
        Path to Obsidian vault directory
    """
    env_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    
    # Default to project directory - user can add this to iCloud Drive
    return PROJECT_ROOT / "obsidian-vault"


def get_obsidian_project_folder() -> Optional[str]:
    """Get the project folder name within the Obsidian vault.
    
    Reads from OBSIDIAN_PROJECT_FOLDER environment variable.
    If empty string or not set, returns None (save directly to vault root).
    
    Returns:
        Project folder name, or None to save to vault root
    """
    folder = os.getenv("OBSIDIAN_PROJECT_FOLDER")
    if folder and folder.strip():
        return folder
    return None


def get_obsidian_project_path() -> Path:
    """Get the full path to the project folder in Obsidian vault.
    
    Returns:
        Path to project folder in Obsidian vault (or vault root if no project folder)
    """
    vault_path = get_obsidian_vault_path()
    project_folder = get_obsidian_project_folder()
    if project_folder:
        return vault_path / project_folder
    return vault_path


def get_log_level() -> str:
    """Get the logging level.
    
    Reads from LOG_LEVEL environment variable, or defaults to 'INFO'.
    
    Returns:
        Logging level string
    """
    return os.getenv("LOG_LEVEL", "INFO").upper()




def get_politician_watchlist_path() -> Path:
    """Get path to politician watchlist YAML file.
    
    Returns:
        Path to politicians.yaml config file
    """
    return PROJECT_ROOT / "config" / "politicians.yaml"


def get_politician_signal_lookback_days() -> int:
    """Get number of days to look back for politician trades in signals.
    
    Reads from POLITICIAN_SIGNAL_LOOKBACK_DAYS environment variable,
    defaults to 45 days (typical STOCK Act filing window).
    
    Returns:
        Number of days to look back
    """
    return int(os.getenv("POLITICIAN_SIGNAL_LOOKBACK_DAYS", "45"))


# Convenience constants
STORAGE_PATH = get_storage_path()
OBSIDIAN_VAULT_PATH = get_obsidian_vault_path()
OBSIDIAN_PROJECT_PATH = get_obsidian_project_path()
RESEARCH_PATH = PROJECT_ROOT / "research"
POLITICIAN_WATCHLIST_PATH = get_politician_watchlist_path()
POLITICIAN_SIGNAL_LOOKBACK_DAYS = get_politician_signal_lookback_days()
