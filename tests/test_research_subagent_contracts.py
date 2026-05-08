"""Structural tests for subagent prompt files.

These check that each subagent prompt declares the contract from the
design spec — tools, inputs, outputs, and the hard rules. They do NOT
grade prose quality.
"""

from __future__ import annotations

from pathlib import Path

import pytest  # noqa: F401

AGENTS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "agents"


def _read(name: str) -> str:
    return (AGENTS_DIR / name).read_text()


def test_skeleton_gatherer_has_required_contract():
    body = _read("research-skeleton-gatherer.md")
    # Frontmatter
    assert body.startswith("---\n")
    assert "name: research-skeleton-gatherer" in body
    # Tools — only the four declared in the spec
    assert "tools:" in body
    for tool in ("WebSearch", "WebFetch", "Read", "Write"):
        assert tool in body
    # Output contract
    assert "coverage_core.json" in body
    # Source-type vocabulary from spec
    for st in (
        "filing",
        "earnings-IR",
        "hq-media",
        "competitor-primary",
        "academic-expert",
    ):
        assert st in body
    # Foundational scope items from spec
    assert "10-K" in body
    assert "10-Q" in body
    assert "earnings call" in body.lower()
    # Hard rule: no fabrication
    assert "do not invent" in body.lower() or "do not fabricate" in body.lower()


def test_section_writer_has_required_contract():
    body = _read("research-section-writer.md")
    assert "name: research-section-writer" in body
    # Tools — writers gain WebSearch for deepening
    for tool in ("WebSearch", "WebFetch", "Read", "Grep", "Write"):
        assert tool in body
    # Two-phase process
    assert "deepen" in body.lower()
    # Cluster names
    for cluster in ("A", "B", "C", "D"):
        assert cluster in body
    # Section taxonomy markers
    for sec in ("§2", "§14", "§20"):
        assert sec in body
    # Citation format
    assert "[src:" in body
    # Fact/Analysis/Inference labels
    assert "**Fact**" in body
    assert "**Analysis**" in body
    assert "**Inference**" in body
    # Hard grounding rule (numerical claim without cite -> Inference)
    assert "must be tagged" in body.lower() or "must tag" in body.lower()
