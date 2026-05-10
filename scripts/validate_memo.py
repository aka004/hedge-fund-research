#!/usr/bin/env python3
"""Validate the structural integrity of a memo.md.

Reads <working_dir>/memo.md and <working_dir>/coverage_log.json.
Prints each check result. Exits 0 if all PASS, 1 if any FAIL.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `from research.memo_validate import ...` when invoked as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.memo_validate import validate_memo  # noqa: E402


def main(working_dir: Path) -> int:
    memo_path = working_dir / "memo.md"
    coverage_path = working_dir / "coverage_log.json"

    if not memo_path.exists():
        print(f"FAIL: {memo_path} not found", file=sys.stderr)
        return 1
    if not coverage_path.exists():
        print(f"FAIL: {coverage_path} not found", file=sys.stderr)
        return 1

    results = validate_memo(memo_path, coverage_path)
    any_failed = False
    for r in results:
        line = f"[{r['status']}] {r['check']}"
        if r.get("message"):
            line += f" — {r['message']}"
        print(line)
        if r["status"] == "FAIL":
            any_failed = True
    return 1 if any_failed else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: validate_memo.py <working_dir>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
