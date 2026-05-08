"""Integration tests for the merge_coverage and validate_memo CLI wrappers."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parent.parent


def _row(link: str, source_type: str = "filing", date_str: str = "2025-09-01"):
    return {
        "id": 1,
        "title": link,
        "link": link,
        "date": date_str,
        "source_type": source_type,
        "region": "US",
        "domain": link.split("/")[2],
        "section": "x",
        "note": "",
        "recency": "Yes",
    }


def test_merge_coverage_cli_writes_log_and_validator(tmp_path: Path):
    core = [
        _row("https://sec.gov/10k", "filing"),
        _row("https://bloomberg.com/x", "hq-media", "2025-12-01"),
    ]
    (tmp_path / "coverage_core.json").write_text(json.dumps(core))
    for cluster in ("A", "B", "C", "D"):
        (tmp_path / f"coverage_{cluster}.json").write_text("[]")

    result = subprocess.run(
        [sys.executable, "scripts/merge_coverage.py", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    log = json.loads((tmp_path / "coverage_log.json").read_text())
    assert len(log) == 2
    assert all(r["scope"] == "core" for r in log)

    validator = json.loads((tmp_path / "coverage_validator.json").read_text())
    rules = {v["rule"] for v in validator}
    assert rules == {
        "min_60_sources",
        "min_10_hq_media",
        "min_5_competitor_primary",
        "min_5_academic_expert",
        "min_60pct_recent",
        "max_10pct_per_domain",
    }
    min_sources = next(v for v in validator if v["rule"] == "min_60_sources")
    assert min_sources["status"] == "FAIL"


def test_merge_coverage_cli_handles_missing_fragment_files(tmp_path: Path):
    """Missing fragment files are treated as empty (graceful)."""
    (tmp_path / "coverage_core.json").write_text(
        json.dumps([_row("https://sec.gov/x")])
    )
    # Note: A/B/C/D fragments deliberately not created.
    result = subprocess.run(
        [sys.executable, "scripts/merge_coverage.py", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    log = json.loads((tmp_path / "coverage_log.json").read_text())
    assert len(log) == 1
