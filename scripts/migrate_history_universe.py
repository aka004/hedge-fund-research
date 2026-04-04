#!/usr/bin/env python3
"""One-time migration: copy existing history to universe-scoped path, backfill universe field."""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import STORAGE_PATH

old_path = STORAGE_PATH / "alpha_gpt_history.json"
new_path = STORAGE_PATH / "alpha_gpt_history_sp500.json"

if not old_path.exists():
    print(f"No history at {old_path} — nothing to migrate")
    sys.exit(0)

history = json.loads(old_path.read_text())
for e in history:
    e.setdefault("universe", "sp500")

new_path.write_text(json.dumps(history, indent=2))
print(f"Migrated {len(history)} entries → {new_path}")
# Keep old file as backup
shutil.copy(old_path, old_path.with_suffix(".json.bak"))
print(f"Backup at {old_path.with_suffix('.json.bak')}")
