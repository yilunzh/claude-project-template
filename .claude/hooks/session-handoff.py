#!/usr/bin/env python3
"""Stop hook: Detect incomplete work and require handoff.

Uses multiple signals:
1. Git status (uncommitted changes)
2. Step counter (edits without checkpoint)
3. Transcript patterns (in_progress todos)

Blocks if 2+ signals detected, advisory warning if 1 signal.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import get_changed_files, get_project_dir, handoff_recent, is_code_file


def get_uncommitted_changes():
    """Check git for uncommitted code changes to tracked files."""
    all_changed = get_changed_files()
    skip = [".claude/", "requirements", ".env", ".gitignore", "package-lock.json"]
    return [
        f for f in all_changed
        if is_code_file(f) and not any(p in f for p in skip)
    ]


def get_step_count():
    """Read step counter to see edit activity."""
    counter_path = Path(get_project_dir()) / ".claude" / ".step-counter"

    if not counter_path.exists():
        return 0

    try:
        with open(counter_path, "r") as f:
            data = json.load(f)
            return data.get("count", 0)
    except (json.JSONDecodeError, IOError):
        return 0


def check_transcript_for_incomplete_todos():
    """Check transcript for in_progress todo items.

    Looks for in_progress status patterns that appear near TodoWrite or
    TaskUpdate tool calls, rather than bare substring matching which
    could false-positive on unrelated text.
    """
    transcript = os.environ.get("CLAUDE_TRANSCRIPT", "")

    if not transcript:
        return False

    # Look for in_progress status near task tool context
    task_contexts = ["TodoWrite", "TaskUpdate", "TaskCreate", "todo"]
    has_task_context = any(ctx in transcript for ctx in task_contexts)

    if not has_task_context:
        return False

    # Now check for in_progress patterns
    in_progress_pattern = '"status": "in_progress"'
    alt_pattern = "'status': 'in_progress'"

    if in_progress_pattern not in transcript and alt_pattern not in transcript:
        return False

    # Find last in_progress and check if it was later completed
    last_in_progress = transcript.rfind("in_progress")
    remaining = transcript[last_in_progress:]
    return "completed" not in remaining[:500].lower()


def main():
    # Skip if handoff already written
    if handoff_recent():
        return {"continue": True}

    # Collect signals
    signals = []

    # Signal 1: Uncommitted code changes
    uncommitted = get_uncommitted_changes()
    if uncommitted:
        file_list = ", ".join(uncommitted[:5])
        if len(uncommitted) > 5:
            file_list += f" (+{len(uncommitted) - 5} more)"
        signals.append(f"Uncommitted changes: {file_list}")

    # Signal 2: High step count without recent checkpoint
    step_count = get_step_count()
    if step_count >= 3:
        signals.append(f"{step_count} edits since last checkpoint")

    # Signal 3: In-progress todos
    if check_transcript_for_incomplete_todos():
        signals.append("Active in_progress todo items")

    # Require 2+ signals to block (reduces false positives)
    if len(signals) >= 2:
        return {
            "continue": False,
            "stopReason": (
                "Incomplete work detected:\n"
                + "\n".join(f"  - {s}" for s in signals)
                + "\n\nWrite .claude/handoff.md before ending session with:\n"
                "  - What we were doing\n"
                "  - Where we stopped\n"
                "  - Key decisions\n"
                "  - Next steps"
            ),
        }

    # Single signal: advisory warning only
    if len(signals) == 1:
        return {
            "continue": True,
            "message": (
                f"Note: {signals[0]}. Consider writing "
                ".claude/handoff.md if work is incomplete."
            ),
        }

    return {"continue": True}


if __name__ == "__main__":
    print(json.dumps(main()))
