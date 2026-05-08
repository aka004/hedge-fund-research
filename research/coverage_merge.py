"""Deterministic union-and-dedupe of coverage fragments.

This module is the orchestrator's deterministic glue between the
skeleton-gatherer and the per-cluster writers. It must not be done
by an LLM agent — dedupe and validator counts must be reproducible.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
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


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def run_validator(
    merged: list[dict[str, Any]],
    today: date,
) -> list[dict[str, Any]]:
    """Run the six coverage-validator rules against the merged set.

    Returns a list of {rule, value, threshold, status} entries.
    """
    n = len(merged)
    results: list[dict[str, Any]] = []

    def add(rule: str, value: Any, threshold: Any, passed: bool) -> None:
        results.append(
            {
                "rule": rule,
                "value": value,
                "threshold": threshold,
                "status": "PASS" if passed else "FAIL",
            }
        )

    add("min_60_sources", n, 60, n >= 60)

    hq = sum(1 for r in merged if r.get("source_type") == "hq-media")
    add("min_10_hq_media", hq, 10, hq >= 10)

    comp = sum(1 for r in merged if r.get("source_type") == "competitor-primary")
    add("min_5_competitor_primary", comp, 5, comp >= 5)

    acad = sum(1 for r in merged if r.get("source_type") == "academic-expert")
    add("min_5_academic_expert", acad, 5, acad >= 5)

    recent_count = sum(
        1 for r in merged if _months_between(_parse_date(r["date"]), today) <= 24
    )
    ratio = recent_count / n if n else 0.0
    add("min_60pct_recent", ratio, 0.6, ratio >= 0.6)

    if n:
        domain_counts = Counter(r["domain"] for r in merged)
        max_pct = max(domain_counts.values()) / n
    else:
        max_pct = 0.0
    add("max_10pct_per_domain", max_pct, 0.10, max_pct <= 0.10)

    return results
