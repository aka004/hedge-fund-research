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


def test_verifier_has_required_contract():
    body = _read("research-verifier.md")
    assert "name: research-verifier" in body
    # Tools — note: NO WebSearch (verifier only re-fetches cited URLs)
    for tool in ("WebFetch", "Read", "Write"):
        assert tool in body
    assert "WebSearch" not in body  # verifier should not search; it re-fetches
    # Output file
    assert "verification_report.json" in body
    # Verdicts
    for v in (
        "VERIFIED",
        "SUPPORTED",
        "UNSUPPORTED",
        "MISSING_CITATION",
        "STALE",
        "UNVERIFIABLE_NETWORK",
    ):
        assert v in body
    # Hard rule: NO edits to section files
    assert (
        "no edit" in body.lower()
        or "do not edit" in body.lower()
        or "do not modify" in body.lower()
    )


def test_synthesizer_has_required_contract():
    body = _read("research-synthesizer.md")
    assert "name: research-synthesizer" in body
    # Tools — Read + Write only, NO web tools
    assert "WebSearch" not in body
    assert "WebFetch" not in body
    for tool in ("Read", "Write"):
        assert tool in body
    # Output files
    assert "memo.md" in body
    assert "appendix.md" in body
    # Section ownership: synthesizer authors §1 and §21
    assert "§1" in body and "§21" in body
    # Decision rules
    assert "E[TR]" in body
    for gate in ("Margin of Safety", "Skew", "Why-now", "Quality"):
        assert gate.lower() in body.lower()
    # Refusal pattern
    assert "cannot be Buy" in body or "cannot be **Buy**" in body
    # Quality scorecard subscores
    for s in ("Market", "Moat", "Unit Economics", "Execution", "Financial Quality"):
        assert s in body
    # Header format
    assert "Quality = " in body and "Entry = " in body


COMMANDS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "commands"


def test_research_command_has_required_orchestration_steps():
    body = (COMMANDS_DIR / "research.md").read_text()
    # Frontmatter
    assert body.startswith("---\n")
    # Argument
    assert "TICKER" in body or "$ARGUMENTS" in body
    # Subagent dispatch (all four)
    for agent in (
        "research-skeleton-gatherer",
        "research-section-writer",
        "research-verifier",
        "research-synthesizer",
    ):
        assert agent in body
    # Parallelism for writers
    assert "parallel" in body.lower() or "single message" in body.lower()
    # Cluster fan-out (all 4 letters present)
    for cluster in (
        "cluster_name=A",
        "cluster_name=B",
        "cluster_name=C",
        "cluster_name=D",
    ):
        # Allow alternate punctuation
        letter = cluster.split("=")[1]
        assert f"={letter}" in body or f'"{letter}"' in body or f"'{letter}'" in body
    # Merge step via Bash
    assert "scripts/merge_coverage.py" in body
    # Validator inspection
    assert "coverage_validator.json" in body
    # Working dir convention
    assert "output/research" in body
