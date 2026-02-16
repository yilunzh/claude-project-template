#!/usr/bin/env python3
"""
Warns about uncommitted changes at session start.
Runs on first user prompt to catch forgotten work from previous sessions.
Advisory only - doesn't block.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import log_metric, session_once


def get_uncommitted_changes():
    """Get list of uncommitted changes from git."""
    try:
        # Get modified files (staged and unstaged)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=os.environ.get("CLAUDE_PROJECT_DIR", "."),
        )
        if result.returncode != 0:
            return []

        changes = []
        for line in result.stdout.strip().split("\n"):
            if line:
                status = line[:2]
                filepath = line[3:]
                # Skip untracked files and common noise
                if status.strip() == "??":
                    # Only warn about untracked files that look important
                    if any(
                        filepath.endswith(ext)
                        for ext in [".py", ".html", ".js", ".css", ".json"]
                    ):
                        if not any(
                            skip in filepath
                            for skip in ["__pycache__", ".pyc", "node_modules", ".bak"]
                        ):
                            changes.append(f"  ?? {filepath} (untracked)")
                else:
                    changes.append(f"  {status} {filepath}")
        return changes
    except Exception:
        return []


def main():
    # Only show once per session
    if not session_once("uncommitted-warning-shown"):
        log_metric(
            "uncommitted-changes-check", "skip", "auto", "skip",
            "already shown this session",
        )
        return {"continue": True}

    changes = get_uncommitted_changes()

    if not changes:
        log_metric("uncommitted-changes-check", "run", "auto", "allow", "no changes")
        return {"continue": True}

    # Build warning message
    change_list = "\n".join(changes[:10])  # Limit to 10 files
    extra = f"\n  ... and {len(changes) - 10} more" if len(changes) > 10 else ""

    detail = f"{len(changes)} uncommitted changes"
    log_metric("uncommitted-changes-check", "run", "auto", "advisory", detail)
    return {
        "continue": True,
        "message": f"""Uncommitted changes detected.

The following files have uncommitted changes from a previous session:
{change_list}{extra}

Consider:
- Committing these changes if they're ready
- Stashing them: git stash push -m "WIP: description"
- Discarding them: git restore <file>""",
    }


if __name__ == "__main__":
    print(json.dumps(main()))
