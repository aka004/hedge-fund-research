"""Unit tests for research.coverage_merge."""

from __future__ import annotations

from datetime import date

import pytest

from research.coverage_merge import merge_fragments, run_validator


def make_row(
    *,
    id: int = 1,
    title: str = "doc",
    link: str = "https://example.com/a",
    date_str: str = "2025-09-01",
    source_type: str = "filing",
    domain: str | None = None,
):
    return {
        "id": id,
        "title": title,
        "link": link,
        "date": date_str,
        "source_type": source_type,
        "region": "US",
        "domain": domain or link.split("/")[2],
        "section": "x",
        "note": "",
        "recency": "Yes",
    }


# ---------- merge_fragments ----------


def test_merge_empty_returns_empty():
    result = merge_fragments(core=[], fragments={})
    assert result == {"sources": [], "aliases": {}}


def test_merge_attaches_scope_to_core_rows():
    core = [make_row(link="https://sec.gov/abc")]
    result = merge_fragments(core=core, fragments={})
    assert len(result["sources"]) == 1
    assert result["sources"][0]["scope"] == "core"
    assert result["aliases"] == {}


def test_merge_attaches_scope_to_writer_fragments():
    fragments = {
        "A": [make_row(link="https://example.com/a")],
        "B": [make_row(link="https://example.com/b")],
    }
    result = merge_fragments(core=[], fragments=fragments)
    assert sorted(r["scope"] for r in result["sources"]) == ["A", "B"]
    assert result["aliases"] == {}


def test_merge_orders_core_before_writer_fragments():
    core = [make_row(link="https://sec.gov/x")]
    fragments = {"A": [make_row(link="https://example.com/a")]}
    result = merge_fragments(core=core, fragments=fragments)
    assert result["sources"][0]["scope"] == "core"
    assert result["sources"][1]["scope"] == "A"


def test_dedupe_drops_later_scope_duplicate_link():
    core = [make_row(id=7, link="https://sec.gov/10k")]
    fragments = {"A": [make_row(id=3, link="https://sec.gov/10k", title="mirror")]}
    result = merge_fragments(core=core, fragments=fragments)
    assert len(result["sources"]) == 1
    assert result["sources"][0]["scope"] == "core"
    assert result["sources"][0]["dedupe_origin"] == ["A"]


def test_dedupe_records_multiple_dropped_scopes():
    core = [make_row(link="https://sec.gov/10k")]
    fragments = {
        "A": [make_row(link="https://sec.gov/10k")],
        "B": [make_row(link="https://sec.gov/10k")],
    }
    result = merge_fragments(core=core, fragments=fragments)
    assert len(result["sources"]) == 1
    assert sorted(result["sources"][0]["dedupe_origin"]) == ["A", "B"]


def test_dedupe_does_not_drop_distinct_urls():
    core = [make_row(link="https://sec.gov/10k")]
    fragments = {"A": [make_row(link="https://sec.gov/10q")]}
    result = merge_fragments(core=core, fragments=fragments)
    assert len(result["sources"]) == 2


def test_dedupe_within_same_fragment():
    fragments = {
        "A": [make_row(link="https://x.com/p"), make_row(link="https://x.com/p")]
    }
    result = merge_fragments(core=[], fragments=fragments)
    assert len(result["sources"]) == 1
    assert result["sources"][0]["dedupe_origin"] == ["A"]


# ---------- aliases (new) ----------


def test_aliases_records_cluster_into_core_collapse():
    """B:1 collapsed into core:7 (shared URL) → aliases["B:1"] = "core:7"."""
    core = [make_row(id=7, link="https://sec.gov/10k", title="primary")]
    fragments = {"B": [make_row(id=1, link="https://sec.gov/10k", title="mirror")]}
    result = merge_fragments(core=core, fragments=fragments)
    assert result["aliases"] == {"B:1": "core:7"}
    # Direct-source rows are unchanged in identity; only `dedupe_origin` added.
    assert result["sources"][0]["scope"] == "core"
    assert result["sources"][0]["id"] == 7
    assert result["sources"][0]["title"] == "primary"


def test_aliases_records_cluster_into_earlier_cluster_collapse():
    """B:4 collapsed into A:14 — alias points across cluster boundary."""
    fragments = {
        "A": [make_row(id=14, link="https://example.com/p")],
        "B": [make_row(id=4, link="https://example.com/p")],
    }
    result = merge_fragments(core=[], fragments=fragments)
    assert result["aliases"] == {"B:4": "A:14"}


def test_aliases_records_multiple_collapses():
    """Independent collapses each get their own alias entry."""
    core = [
        make_row(id=7, link="https://sec.gov/10k"),
        make_row(id=19, link="https://ir.example.com/transcript"),
    ]
    fragments = {
        "B": [
            make_row(id=1, link="https://sec.gov/10k"),
            make_row(id=13, link="https://ir.example.com/transcript"),
        ],
        "C": [make_row(id=18, link="https://sec.gov/10k")],
    }
    result = merge_fragments(core=core, fragments=fragments)
    assert result["aliases"] == {
        "B:1": "core:7",
        "B:13": "core:19",
        "C:18": "core:7",
    }


def test_aliases_empty_when_no_dedupe():
    core = [make_row(id=1, link="https://sec.gov/a")]
    fragments = {"A": [make_row(id=2, link="https://sec.gov/b")]}
    result = merge_fragments(core=core, fragments=fragments)
    assert result["aliases"] == {}


def test_aliases_does_not_self_alias_within_same_fragment():
    """Two rows with id=5 in cluster A on same URL — surviving row doesn't
    self-alias 'A:5' → 'A:5'."""
    fragments = {
        "A": [
            make_row(id=5, link="https://x.com/p"),
            make_row(id=5, link="https://x.com/p"),
        ]
    }
    result = merge_fragments(core=[], fragments=fragments)
    assert result["aliases"] == {}


# ---------- run_validator ----------

TODAY = date(2026, 5, 8)


def _result(results: list[dict], rule: str) -> dict:
    return next(r for r in results if r["rule"] == rule)


def test_validator_min_60_sources_fail():
    merged = [make_row() for _ in range(59)]
    r = _result(run_validator(merged, TODAY), "min_60_sources")
    assert r["status"] == "FAIL"
    assert r["value"] == 59
    assert r["threshold"] == 60


def test_validator_min_60_sources_pass():
    merged = [make_row(domain=f"d{i}.com") for i in range(60)]
    r = _result(run_validator(merged, TODAY), "min_60_sources")
    assert r["status"] == "PASS"


def test_validator_min_10_hq_media_fail():
    rows = [make_row(source_type="hq-media") for _ in range(9)] + [
        make_row(domain=f"d{i}.com") for i in range(51)
    ]
    r = _result(run_validator(rows, TODAY), "min_10_hq_media")
    assert r["status"] == "FAIL"
    assert r["value"] == 9


def test_validator_min_5_competitor_primary_pass():
    rows = [make_row(source_type="competitor-primary") for _ in range(5)] + [
        make_row(domain=f"d{i}.com") for i in range(55)
    ]
    r = _result(run_validator(rows, TODAY), "min_5_competitor_primary")
    assert r["status"] == "PASS"


def test_validator_min_5_academic_expert_fail():
    rows = [make_row(source_type="academic-expert") for _ in range(4)] + [
        make_row(domain=f"d{i}.com") for i in range(56)
    ]
    r = _result(run_validator(rows, TODAY), "min_5_academic_expert")
    assert r["status"] == "FAIL"


def test_validator_recency_fail_when_under_60pct_within_24m():
    recent = [make_row(date_str="2025-06-01", domain=f"r{i}.com") for i in range(30)]
    old = [make_row(date_str="2023-01-01", domain=f"o{i}.com") for i in range(30)]
    r = _result(run_validator(recent + old, TODAY), "min_60pct_recent")
    assert r["status"] == "FAIL"
    assert r["value"] == pytest.approx(0.5)


def test_validator_recency_pass_when_60pct_within_24m():
    recent = [make_row(date_str="2025-06-01", domain=f"r{i}.com") for i in range(36)]
    old = [make_row(date_str="2023-01-01", domain=f"o{i}.com") for i in range(24)]
    r = _result(run_validator(recent + old, TODAY), "min_60pct_recent")
    assert r["status"] == "PASS"


def test_validator_domain_concentration_fail_above_10pct():
    rows = [make_row(domain="dominant.com") for _ in range(7)] + [
        make_row(domain=f"other{i}.com") for i in range(53)
    ]
    r = _result(run_validator(rows, TODAY), "max_10pct_per_domain")
    assert r["status"] == "FAIL"


def test_validator_domain_concentration_pass_at_10pct():
    rows = [make_row(domain="dominant.com") for _ in range(6)] + [
        make_row(domain=f"other{i}.com") for i in range(54)
    ]
    r = _result(run_validator(rows, TODAY), "max_10pct_per_domain")
    assert r["status"] == "PASS"
