import subprocess
import sys
from pathlib import Path


def test_verify_paper_safety_exits_zero():
    """
    Basic smoke test: cli.py verify-paper-safety should pass in Phase 1.
    """
    repo_root = Path(__file__).parent.parent
    cli_path = repo_root / "cli.py"

    result = subprocess.run(
        [sys.executable, str(cli_path), "verify-paper-safety"],
        cwd=str(repo_root),
    )
    assert result.returncode == 0

