"""Tests for the migrate_derived_tables script.

Closes the HIGH finding from the 2026-05-13 code review: the migration
loop had no `--dry-run` flag and no transaction wrapper, so a partial
failure mid-loop left the schema in an indeterminate state.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def _load_migration_module(tmp_path):
    """Load migrate_derived_tables with RESEARCH_DB_PATH pointed at tmp."""
    # Patch config before import.
    db_file = tmp_path / "test.duckdb"
    with patch.dict(sys.modules, {}, clear=False):
        # Patch config module's RESEARCH_DB_PATH
        import config

        with patch.object(config, "RESEARCH_DB_PATH", db_file):
            spec = importlib.util.spec_from_file_location(
                "migrate_derived_tables",
                project_root / "scripts" / "migrate_derived_tables.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod, db_file


class TestDryRun:
    def test_dry_run_does_not_create_tables(self, tmp_path, monkeypatch, capsys):
        mod, db_file = _load_migration_module(tmp_path)
        monkeypatch.setattr(sys, "argv", ["migrate_derived_tables.py", "--dry-run"])

        # check_db_reachable returns True for the tmp path's parent
        with patch.object(mod, "check_db_reachable", return_value=True):
            try:
                mod.migrate()
            except SystemExit:
                pass  # script may sys.exit(0) on success

        # No DB file should have been created.
        assert not db_file.exists(), "dry-run created the DB file"


class TestRollbackOnFailure:
    def test_partial_failure_rolls_back_created_tables(self, tmp_path, monkeypatch):
        mod, db_file = _load_migration_module(tmp_path)

        # Inject a deliberately broken DDL in the middle of the dict
        # to force a failure mid-migration.
        broken = dict(mod.DERIVED_TABLES)
        # Put the broken DDL after at least one valid one.
        keys = list(broken.keys())
        broken[keys[0]] = broken[keys[0]]  # keep first one
        # Append a deliberately invalid DDL
        broken["__broken__"] = "CREATE TABLE __broken__ (col INVALID_TYPE_XYZ)"

        monkeypatch.setattr(mod, "DERIVED_TABLES", broken)
        monkeypatch.setattr(sys, "argv", ["migrate_derived_tables.py"])

        with patch.object(mod, "check_db_reachable", return_value=True):
            with pytest.raises(SystemExit):
                mod.migrate()

        # After rollback the previously-created tables should NOT exist.
        # (Pre-fix: partial state left them in place.)
        if db_file.exists():
            con = duckdb.connect(str(db_file), read_only=True)
            existing = {
                row[0]
                for row in con.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                ).fetchall()
            }
            con.close()
            # The first table's name from the original mapping should
            # not have been committed.
            first_table = keys[0]
            assert first_table not in existing, (
                f"partial migration left {first_table} behind after failure; "
                f"existing: {existing}"
            )
