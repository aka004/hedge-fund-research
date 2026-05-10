"""Structural validator for the final memo.md.

Checks the memo conforms to the spec contract — does NOT grade the
analysis. Failures here are bugs (orchestrator or subagent prompts
producing malformed output), not LLM-variance noise.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CITATION_RE = re.compile(r"\[src:(?P<scope>[A-Za-z]+):(?P<id>\d+)\]")
FACT_PARA_RE = re.compile(r"^\*\*Fact\*\*", re.MULTILINE)
GATE_HEADER_RE = re.compile(r"Quality\s*=\s*\d{1,3}/100\s*\|\s*Entry\s*=")


def _result(check: str, status: str, message: str = "") -> dict[str, str]:
    return {"check": check, "status": status, "message": message}


def _split_paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def _exec_summary_first(memo: str) -> dict[str, str]:
    headings = [
        (m.start(), m.group(1).strip())
        for m in re.finditer(r"^##\s+(.+)$", memo, re.MULTILINE)
    ]
    if not headings:
        return _result("exec_summary_first", "FAIL", "no `## ` headings found")
    first_heading = headings[0][1].lower()
    if "executive summary" in first_heading:
        return _result("exec_summary_first", "PASS")
    return _result(
        "exec_summary_first",
        "FAIL",
        f"first ## heading was '{headings[0][1]}', expected Executive Summary",
    )


def _gate_header_present(memo: str) -> dict[str, str]:
    if GATE_HEADER_RE.search(memo):
        return _result("gate_header_present", "PASS")
    return _result(
        "gate_header_present",
        "FAIL",
        "no line matching 'Quality = NN/100 | Entry = ...' found",
    )


def _fact_paragraphs_cited(memo: str) -> dict[str, str]:
    paras = _split_paragraphs(memo)
    uncited = [p for p in paras if FACT_PARA_RE.match(p) and not CITATION_RE.search(p)]
    if not uncited:
        return _result("fact_paragraphs_cited", "PASS")
    return _result(
        "fact_paragraphs_cited",
        "FAIL",
        f"{len(uncited)} Fact paragraph(s) lack a [src:scope:n] citation",
    )


def _citations_resolve(
    memo: str,
    sources: list[dict[str, Any]],
    aliases: dict[str, str],
) -> dict[str, str]:
    """Pass when every cited [src:scope:id] resolves to a source row,
    either directly or via the aliases map (a `<dropped>` → `<survivor>`
    record from the coverage merge step)."""
    available = {(row["scope"], int(row["id"])) for row in sources}
    referenced = [
        (m.group("scope"), int(m.group("id"))) for m in CITATION_RE.finditer(memo)
    ]
    missing: set[tuple[str, int]] = set()
    for scope, ident in referenced:
        if (scope, ident) in available:
            continue
        target = aliases.get(f"{scope}:{ident}")
        if target is not None:
            try:
                t_scope, t_id_str = target.split(":", 1)
                if (t_scope, int(t_id_str)) in available:
                    continue
            except (ValueError, AttributeError):
                pass
        missing.add((scope, ident))
    if not missing:
        return _result("citations_resolve", "PASS")
    formatted = ", ".join(f"[src:{s}:{i}]" for s, i in sorted(missing))
    return _result("citations_resolve", "FAIL", f"unresolved citations: {formatted}")


def _coverage_log_appended(memo: str) -> dict[str, str]:
    if re.search(r"^##\s+Coverage Log", memo, re.MULTILINE):
        return _result("coverage_log_appended", "PASS")
    return _result(
        "coverage_log_appended",
        "FAIL",
        "no '## Coverage Log' heading found",
    )


def validate_memo(memo_path: Path, coverage_log_path: Path) -> list[dict[str, str]]:
    """Run all structural checks on the memo. Returns list of results.

    Accepts both coverage_log.json schemas:
    - new: {"sources": [...], "aliases": {...}}
    - legacy: [<row>, ...] — treated as sources with empty aliases.
    """
    memo = memo_path.read_text()
    raw = json.loads(coverage_log_path.read_text())
    if isinstance(raw, dict):
        sources = raw.get("sources", [])
        aliases = raw.get("aliases", {})
    else:
        sources = raw
        aliases = {}
    return [
        _exec_summary_first(memo),
        _gate_header_present(memo),
        _fact_paragraphs_cited(memo),
        _citations_resolve(memo, sources, aliases),
        _coverage_log_appended(memo),
    ]
