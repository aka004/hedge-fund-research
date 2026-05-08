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
