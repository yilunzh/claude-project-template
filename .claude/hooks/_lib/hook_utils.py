"""Shared utilities for Claude Code hooks.

Consolidates common patterns: git operations, file filtering,
JSON I/O, and checkpoint/handoff freshness checks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


def get_project_dir() -> str:
    """Get project directory from environment."""
    return os.environ.get("CLAUDE_PROJECT_DIR", ".")


def get_current_branch(project_dir: str | None = None) -> str:
    """Get current git branch name.

    Returns empty string on error (detached HEAD, not a git repo, etc.).
    """
    cwd = project_dir or get_project_dir()
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def get_changed_files(
    project_dir: str | None = None,
    staged_only: bool = False,
) -> list[str]:
    """Get changed files from git.

    Args:
        project_dir: Project root directory.
        staged_only: If True, only return staged files. Otherwise staged + unstaged.
    """
    cwd = project_dir or get_project_dir()
    files: set[str] = set()

    try:
        if staged_only:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                cwd=cwd,
            )
            files.update(f for f in result.stdout.strip().split("\n") if f)
        else:
            # Staged
            staged = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                cwd=cwd,
            )
            files.update(f for f in staged.stdout.strip().split("\n") if f)

            # Unstaged
            unstaged = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True,
                text=True,
                cwd=cwd,
            )
            files.update(f for f in unstaged.stdout.strip().split("\n") if f)
    except Exception:
        pass

    return sorted(files)


# ---------- File filtering ----------

# Canonical extension and skip lists, shared across hooks.
CODE_EXTENSIONS = [
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".go", ".rs",
]

SKIP_PATTERNS = [
    "test_",
    "_test.",
    ".test.",
    "tests/",
    "__pycache__",
    ".claude/",
    ".gitignore",
    "README",
    "BRIEF.md",
    "CLAUDE.md",
    "SPEC.md",
    "PATTERNS.md",
    ".json",
    ".toml",
    ".cfg",
    ".ini",
    ".yml",
    ".yaml",
    ".lock",
    ".md",
]

# Additional patterns to skip for step-counting (config/infra files)
STEP_SKIP_PATTERNS = [
    "test_",
    ".spec.",
    ".claude/",
    "requirements",
    "package.json",
    "package-lock.json",
    ".env",
    "session-context.md",
    "handoff.md",
    ".step-counter",
    ".gitignore",
    "pytest.ini",
    "conftest.py",
    "tsconfig.json",
    "vite.config",
    "jest.config",
]


def filter_source_files(files: list[str]) -> list[str]:
    """Filter to source files only (exclude tests, config, .claude/).

    Uses SKIP_PATTERNS — anything matching is excluded.
    """
    return [
        f for f in files
        if not any(pattern in f for pattern in SKIP_PATTERNS)
    ]


def is_code_file(file_path: str) -> bool:
    """Check if file is a code file by extension."""
    return any(file_path.endswith(ext) for ext in CODE_EXTENSIONS)


def is_major_step(file_path: str) -> bool:
    """Determine if an edit to this file constitutes a major step.

    Used by checkpoint-reminder to decide whether to increment counter.
    """
    if any(pattern in file_path for pattern in STEP_SKIP_PATTERNS):
        return False
    return is_code_file(file_path)


# ---------- JSON I/O ----------

def read_json_stdin() -> dict:
    """Read and parse JSON from stdin (hook input).

    Returns empty dict on parse failure or empty input.
    """
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


# ---------- Checkpoint / handoff freshness ----------

def checkpoint_recent(project_dir: str | None = None, minutes: int = 10) -> bool:
    """Check if session-context.md was updated within `minutes`."""
    cwd = project_dir or get_project_dir()
    path = Path(cwd) / ".claude" / "session-context.md"

    if not path.exists():
        return False

    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - mtime < timedelta(minutes=minutes)


def handoff_recent(project_dir: str | None = None, minutes: int = 5) -> bool:
    """Check if handoff.md was updated within `minutes`."""
    cwd = project_dir or get_project_dir()
    path = Path(cwd) / ".claude" / "handoff.md"

    if not path.exists():
        return False

    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - mtime < timedelta(minutes=minutes)
