"""Shared git helper utilities for memory tools."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("memory-mcp")


def run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    cmd = ["git"] + args
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if check and result.returncode != 0:
        logger.warning(f"Git command failed: {' '.join(cmd)}\n{result.stderr}")
    return result


def get_current_branch(cwd: Path) -> str:
    """Get the current git branch name."""
    result = run_git(["branch", "--show-current"], cwd, check=False)
    return result.stdout.strip() if result.returncode == 0 else "main"
