"""Test CLI flags for auto_research_loop.py parallel execution."""
import subprocess
import sys
from pathlib import Path


def test_parallel_cli_flags_present():
    """--workers, --worker-timeout, --no-parallel must appear in --help."""
    result = subprocess.run(
        [sys.executable, "scripts/auto_research_loop.py", "--help"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 0
    assert "--workers" in result.stdout
    assert "--worker-timeout" in result.stdout
    assert "--no-parallel" in result.stdout
