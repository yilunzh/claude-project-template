#!/usr/bin/env python3
"""
Advisory Stop hook: reminds to run /self-review after large changes.
Triggers when 5+ non-test/non-config source files changed in session.
Always advisory — never blocks.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import filter_source_files, get_project_dir


def get_changed_source_files():
    """Get source files changed relative to main (or recent commits)."""
    project_dir = get_project_dir()

    # Try diff against main first (feature branch workflow)
    for base in ["main", "master"]:
        result = subprocess.run(
            ["git", "diff", base, "--name-only"],
            capture_output=True,
            text=True,
            cwd=project_dir,
        )
        if result.returncode == 0 and result.stdout.strip():
            return filter_source_files(result.stdout.strip().split("\n"))

    # Fallback: check uncommitted + last 5 commits
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~5"],
        capture_output=True,
        text=True,
        cwd=project_dir,
    )
    if result.returncode == 0 and result.stdout.strip():
        return filter_source_files(result.stdout.strip().split("\n"))

    return []


def self_review_already_run():
    """Check transcript for evidence that /self-review was already run."""
    transcript = os.environ.get("CLAUDE_TRANSCRIPT", "")
    if not transcript:
        return False
    return "/self-review" in transcript or "self-review" in transcript.lower()


def main():
    # Always advisory
    if self_review_already_run():
        return {"continue": True}

    source_files = get_changed_source_files()

    if len(source_files) < 5:
        return {"continue": True}

    file_list = "\n".join(f"  - {f}" for f in source_files[:10])
    extra = f"\n  ... and {len(source_files) - 10} more" if len(source_files) > 10 else ""

    return {
        "continue": True,
        "message": f"This session modified {len(source_files)} source files:\n"
        f"{file_list}{extra}\n\n"
        "Consider running `/self-review` to check for security, architecture, "
        "and CI gaps before finishing.",
    }


if __name__ == "__main__":
    print(json.dumps(main()))
