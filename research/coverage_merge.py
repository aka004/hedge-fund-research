"""Deterministic union-and-dedupe of coverage fragments.

This module is the orchestrator's deterministic glue between the
skeleton-gatherer and the per-cluster writers. It must not be done
by an LLM agent — dedupe and validator counts must be reproducible.

Output schema (coverage_log.json):
    {
        "sources": [<row>, ...],   # the deduped rows; each row keeps all
                                   # its original fields plus `scope` and
                                   # an optional `dedupe_origin` list.
        "aliases": {               # ID-mapping for collapsed rows.
            "<dropped_scope>:<dropped_id>": "<survivor_scope>:<survivor_id>",
            ...
        }
    }

`aliases` lets the memo validator resolve a citation like `[src:B:1]`
even when row B:1 was deduped into core:7 because they shared a URL.
The alias map is empty when no dedupe collapses occurred.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any


def merge_fragments(
    core: list[dict[str, Any]],
    fragments: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Union core + writer fragments, attach `scope`, dedupe by `link` URL.

    First-seen wins. The surviving row gains a `dedupe_origin` list naming
    every later scope whose duplicate row was dropped. Each dropped row's
    `<scope>:<id>` is recorded in the `aliases` map pointing at the
    survivor's `<scope>:<id>` — this preserves the citation path for
    cluster IDs that get collapsed into core (or earlier clusters).

    Returns a dict with two keys:
        sources: list[dict] — the deduped rows in insertion order
                              (core first, then clusters A→Z).
        aliases: dict[str, str] — `<dropped>` → `<survivor>` mapping.
    """
    sources: list[dict[str, Any]] = []
    by_link: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}

    def consume(row: dict[str, Any], scope: str) -> None:
        link = row["link"]
        existing = by_link.get(link)
        if existing is not None:
            existing.setdefault("dedupe_origin", []).append(scope)
            dropped_key = f"{scope}:{row['id']}"
            survivor_key = f"{existing['scope']}:{existing['id']}"
            # Same-scope same-id duplicates would self-alias — skip those.
            if dropped_key != survivor_key:
                aliases[dropped_key] = survivor_key
            return
        new_row = {**row, "scope": scope}
        by_link[link] = new_row
        sources.append(new_row)

    for row in core:
        consume(row, "core")
    for scope in sorted(fragments.keys()):
        for row in fragments[scope]:
            consume(row, scope)
    return {"sources": sources, "aliases": aliases}


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def run_validator(
    merged: list[dict[str, Any]],
    today: date,
) -> list[dict[str, Any]]:
    """Run the six coverage-validator rules against the merged source list.

    Takes the deduped `sources` list (not the wrapper dict). Aliased IDs
    are not counted — they were already collapsed into the survivor — so
    domain concentration and the other counts operate on the unique
    surviving rows.

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
