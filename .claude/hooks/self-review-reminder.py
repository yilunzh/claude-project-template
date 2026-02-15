#!/usr/bin/env python3
"""
Advisory Stop hook: reminds to run /self-review and /arch-review after significant changes.

Triggers:
- /self-review: 5+ non-test/non-config source files changed
- /arch-review: 2+ new source files, 3+ directories changed, or any file > 300 lines

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


def get_new_source_files():
    """Get source files that are new (added, not just modified) relative to main."""
    project_dir = get_project_dir()

    for base in ["main", "master"]:
        result = subprocess.run(
            ["git", "diff", base, "--diff-filter=A", "--name-only"],
            capture_output=True,
            text=True,
            cwd=project_dir,
        )
        if result.returncode == 0:
            files = [f for f in result.stdout.strip().split("\n") if f]
            return filter_source_files(files)

    return []


def should_suggest_arch_review(source_files):
    """Check if architectural review would be valuable.

    Returns (should_suggest, reason) tuple.
    """
    project_dir = get_project_dir()

    # Check 1: New source files created (potential new modules without tests)
    new_files = get_new_source_files()
    if len(new_files) >= 2:
        return True, f"{len(new_files)} new source files created"

    # Check 2: Changes span multiple directories (cross-cutting structural change)
    dirs = set(os.path.dirname(f) for f in source_files if "/" in f)
    if len(dirs) >= 3:
        return True, f"changes span {len(dirs)} directories"

    # Check 3: Any modified file exceeds 300 lines (large module)
    for f in source_files:
        full_path = os.path.join(project_dir, f)
        if os.path.exists(full_path):
            try:
                with open(full_path) as fh:
                    line_count = sum(1 for _ in fh)
                if line_count > 300:
                    return True, f"{f} is over 300 lines"
            except (IOError, UnicodeDecodeError):
                continue

    return False, ""


def review_already_run(command_name):
    """Check transcript for evidence that a review command was already run."""
    transcript = os.environ.get("CLAUDE_TRANSCRIPT", "")
    if not transcript:
        return False
    return f"/{command_name}" in transcript or command_name in transcript.lower()


def main():
    source_files = get_changed_source_files()

    suggest_self_review = len(source_files) >= 5 and not review_already_run("self-review")
    suggest_arch_review, arch_reason = should_suggest_arch_review(source_files)
    if suggest_arch_review and review_already_run("arch-review"):
        suggest_arch_review = False

    if not suggest_self_review and not suggest_arch_review:
        return {"continue": True}

    file_list = "\n".join(f"  - {f}" for f in source_files[:10])
    extra = f"\n  ... and {len(source_files) - 10} more" if len(source_files) > 10 else ""

    parts = [f"This session modified {len(source_files)} source files:\n{file_list}{extra}"]

    if arch_reason:
        parts.append(f"Note: {arch_reason}.")

    parts.append("\nConsider running:")
    if suggest_self_review:
        parts.append("  /self-review — check your diff for security, testing, and CI gaps")
    if suggest_arch_review:
        parts.append("  /arch-review — check codebase structural health")

    return {
        "continue": True,
        "message": "\n".join(parts),
    }


if __name__ == "__main__":
    print(json.dumps(main()))
