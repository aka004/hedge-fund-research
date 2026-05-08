"""Unit tests for research.memo_validate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest  # noqa: F401

from research.memo_validate import validate_memo

# ---- helpers ----

VALID_MEMO = """\
# AAPL — Investment Memo

## Executive Summary

Quality = 78/100 | Entry = Buy

**Fact** Apple reported $383B revenue in FY2024 [src:core:1].

## §1 Thesis Framing

**Analysis** The thesis rests on services growth.

## Coverage Log

(appended)
"""

VALID_COVERAGE = [
    {
        "id": 1,
        "scope": "core",
        "title": "10-K",
        "link": "https://sec.gov/aapl-10k",
        "date": "2024-11-01",
        "source_type": "filing",
        "domain": "sec.gov",
    }
]


def _setup(
    tmp_path: Path, memo: str = VALID_MEMO, coverage: list | None = None
) -> Path:
    (tmp_path / "memo.md").write_text(memo)
    (tmp_path / "coverage_log.json").write_text(
        json.dumps(coverage if coverage is not None else VALID_COVERAGE)
    )
    return tmp_path


# ---- tests ----


def test_valid_memo_passes(tmp_path: Path):
    _setup(tmp_path)
    results = validate_memo(tmp_path / "memo.md", tmp_path / "coverage_log.json")
    assert all(r["status"] == "PASS" for r in results), results


def test_missing_executive_summary_first_fails(tmp_path: Path):
    bad = "# AAPL\n\n## Thesis\n\n## Executive Summary\n\nQuality = 78/100 | Entry = Buy\n\n## Coverage Log\n"
    _setup(tmp_path, memo=bad)
    results = validate_memo(tmp_path / "memo.md", tmp_path / "coverage_log.json")
    failed = [r for r in results if r["status"] == "FAIL"]
    assert any(r["check"] == "exec_summary_first" for r in failed)


def test_missing_gate_header_fails(tmp_path: Path):
    bad = VALID_MEMO.replace("Quality = 78/100 | Entry = Buy", "Quality is good")
    _setup(tmp_path, memo=bad)
    results = validate_memo(tmp_path / "memo.md", tmp_path / "coverage_log.json")
    assert any(
        r["check"] == "gate_header_present" and r["status"] == "FAIL" for r in results
    )


def test_fact_paragraph_without_citation_fails(tmp_path: Path):
    bad = VALID_MEMO.replace("[src:core:1]", "")
    _setup(tmp_path, memo=bad)
    results = validate_memo(tmp_path / "memo.md", tmp_path / "coverage_log.json")
    assert any(
        r["check"] == "fact_paragraphs_cited" and r["status"] == "FAIL" for r in results
    )


def test_unresolvable_citation_fails(tmp_path: Path):
    # Citation [src:core:99] does not exist in coverage_log
    bad = VALID_MEMO.replace("[src:core:1]", "[src:core:99]")
    _setup(tmp_path, memo=bad)
    results = validate_memo(tmp_path / "memo.md", tmp_path / "coverage_log.json")
    assert any(
        r["check"] == "citations_resolve" and r["status"] == "FAIL" for r in results
    )


def test_missing_coverage_log_section_fails(tmp_path: Path):
    bad = VALID_MEMO.replace("## Coverage Log", "## Other Section")
    _setup(tmp_path, memo=bad)
    results = validate_memo(tmp_path / "memo.md", tmp_path / "coverage_log.json")
    assert any(
        r["check"] == "coverage_log_appended" and r["status"] == "FAIL" for r in results
    )
