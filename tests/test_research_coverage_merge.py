"""Unit tests for research.coverage_merge."""

from __future__ import annotations

from research.coverage_merge import merge_fragments, run_validator  # noqa: F401


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
    assert merge_fragments(core=[], fragments={}) == []


def test_merge_attaches_scope_to_core_rows():
    core = [make_row(link="https://sec.gov/abc")]
    result = merge_fragments(core=core, fragments={})
    assert len(result) == 1
    assert result[0]["scope"] == "core"


def test_merge_attaches_scope_to_writer_fragments():
    fragments = {
        "A": [make_row(link="https://example.com/a")],
        "B": [make_row(link="https://example.com/b")],
    }
    result = merge_fragments(core=[], fragments=fragments)
    assert sorted(r["scope"] for r in result) == ["A", "B"]


def test_merge_orders_core_before_writer_fragments():
    core = [make_row(link="https://sec.gov/x")]
    fragments = {"A": [make_row(link="https://example.com/a")]}
    result = merge_fragments(core=core, fragments=fragments)
    assert result[0]["scope"] == "core"
    assert result[1]["scope"] == "A"


def test_dedupe_drops_later_scope_duplicate_link():
    core = [make_row(link="https://sec.gov/10k")]
    fragments = {"A": [make_row(link="https://sec.gov/10k", title="mirror")]}
    result = merge_fragments(core=core, fragments=fragments)
    assert len(result) == 1
    assert result[0]["scope"] == "core"
    assert result[0]["dedupe_origin"] == ["A"]


def test_dedupe_records_multiple_dropped_scopes():
    core = [make_row(link="https://sec.gov/10k")]
    fragments = {
        "A": [make_row(link="https://sec.gov/10k")],
        "B": [make_row(link="https://sec.gov/10k")],
    }
    result = merge_fragments(core=core, fragments=fragments)
    assert len(result) == 1
    assert sorted(result[0]["dedupe_origin"]) == ["A", "B"]


def test_dedupe_does_not_drop_distinct_urls():
    core = [make_row(link="https://sec.gov/10k")]
    fragments = {"A": [make_row(link="https://sec.gov/10q")]}
    result = merge_fragments(core=core, fragments=fragments)
    assert len(result) == 2


def test_dedupe_within_same_fragment():
    fragments = {
        "A": [make_row(link="https://x.com/p"), make_row(link="https://x.com/p")]
    }
    result = merge_fragments(core=[], fragments=fragments)
    assert len(result) == 1
    assert result[0]["dedupe_origin"] == ["A"]
