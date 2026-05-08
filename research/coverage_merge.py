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
    """Union core + writer fragments, attach `scope`, dedupe by `link` URL.

    First-seen wins. The surviving row gains a `dedupe_origin` list naming
    every later scope whose duplicate row was dropped (preserves audit trail
    without inflating validator counts).
    """
    merged: list[dict[str, Any]] = []
    by_link: dict[str, dict[str, Any]] = {}

    def consume(row: dict[str, Any], scope: str) -> None:
        link = row["link"]
        existing = by_link.get(link)
        if existing is not None:
            existing.setdefault("dedupe_origin", []).append(scope)
            return
        new_row = {**row, "scope": scope}
        by_link[link] = new_row
        merged.append(new_row)

    for row in core:
        consume(row, "core")
    for scope in sorted(fragments.keys()):
        for row in fragments[scope]:
            consume(row, scope)
    return merged


def run_validator(*args: object, **kwargs: object) -> None:
    """Validate merged coverage rows against quality gates. Implemented in Task 4."""
    raise NotImplementedError("Implemented in Task 4")
