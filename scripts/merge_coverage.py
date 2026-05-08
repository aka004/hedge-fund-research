#!/usr/bin/env python3
"""Merge coverage fragments and run the coverage validator.

Called by the /research orchestrator slash command between the writer
and verifier phases. Deterministic — never have an LLM do this step.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from research.coverage_merge import merge_fragments, run_validator


def _load_json(path: Path) -> list:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def main(working_dir: Path) -> int:
    core = _load_json(working_dir / "coverage_core.json")
    fragments: dict[str, list] = {
        cluster: _load_json(working_dir / f"coverage_{cluster}.json")
        for cluster in ("A", "B", "C", "D")
    }
    merged = merge_fragments(core=core, fragments=fragments)
    validator = run_validator(merged, today=date.today())

    (working_dir / "coverage_log.json").write_text(json.dumps(merged, indent=2))
    (working_dir / "coverage_validator.json").write_text(
        json.dumps(validator, indent=2)
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: merge_coverage.py <working_dir>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
