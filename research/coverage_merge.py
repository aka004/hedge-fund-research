"""Deterministic union-and-dedupe of coverage fragments.

This module is the orchestrator's deterministic glue between the
skeleton-gatherer and the per-cluster writers. It must not be done
by an LLM agent — dedupe and validator counts must be reproducible.
"""

from __future__ import annotations

from typing import Any


def merge_fragments(
    core: list[dict[str, Any]],
    fragments: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Union core + writer fragments, attaching `scope` to each row.

    Order: core rows first, then fragments in alphabetical scope order.
    """
    merged: list[dict[str, Any]] = []
    for row in core:
        merged.append({**row, "scope": "core"})
    for scope in sorted(fragments.keys()):
        for row in fragments[scope]:
            merged.append({**row, "scope": scope})
    return merged


def run_validator(*args: object, **kwargs: object) -> None:
    """Validate merged coverage rows against quality gates. Implemented in Task 4."""
    raise NotImplementedError("Implemented in Task 4")
