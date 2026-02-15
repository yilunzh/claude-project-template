#!/usr/bin/env python3
"""
Advisory hook: Remind the agent to capture session learnings before ending.

Checks if any memory files were modified today. If not, suggests running
learning_review() to capture session learnings.

Advisory only -- does not block.
"""
import os
from datetime import date
from pathlib import Path


def get_project_root():
    """Get project root from environment or walk up."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parent.parent.parent


def check_memory_activity():
    """Check if any memory files were modified today."""
    project_root = get_project_root()
    memory_dir = project_root / ".claude" / "memory"

    if not memory_dir.exists():
        return False

    today = date.today()

    for subdir in ["corrections", "preferences", "patterns", "reflections"]:
        dir_path = memory_dir / subdir
        if not dir_path.exists():
            continue
        for f in dir_path.iterdir():
            if f.is_file():
                try:
                    mtime = date.fromtimestamp(f.stat().st_mtime)
                    if mtime == today:
                        return True
                except OSError:
                    continue

    return False


def main():
    """Run the memory flush check."""
    if not check_memory_activity():
        print(
            "ADVISORY: No memory activity detected this session. "
            "Consider running learning_review() before ending to capture "
            "session learnings (corrections, preferences, reflections)."
        )
    # If activity detected, stay silent -- no nag needed


if __name__ == "__main__":
    main()
