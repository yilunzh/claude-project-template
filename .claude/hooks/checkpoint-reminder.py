#!/usr/bin/env python3
"""PostToolUse hook: Remind to checkpoint every 3-5 major steps.

Tracks edits via a simple counter file. Advisory only - doesn't block.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import checkpoint_recent, get_project_dir, is_major_step, read_json_stdin


def get_counter_path():
    """Get path to step counter file."""
    return Path(get_project_dir()) / ".claude" / ".step-counter"


def read_counter():
    """Read current step count and last checkpoint time."""
    counter_path = get_counter_path()
    if not counter_path.exists():
        return {"count": 0, "last_checkpoint": None, "last_update": None}

    try:
        with open(counter_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"count": 0, "last_checkpoint": None, "last_update": None}


def write_counter(data):
    """Write step counter data."""
    counter_path = get_counter_path()
    counter_path.parent.mkdir(parents=True, exist_ok=True)

    with open(counter_path, "w") as f:
        json.dump(data, f)


def main():
    # Read hook input
    input_data = read_json_stdin()
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Only count major steps
    if not is_major_step(file_path):
        return {"continue": True}

    # Read and increment counter
    counter = read_counter()
    counter["count"] = counter.get("count", 0) + 1
    counter["last_update"] = datetime.now().isoformat()

    # Check if checkpoint was recently written
    if checkpoint_recent():
        # Reset counter after checkpoint
        counter["count"] = 0
        counter["last_checkpoint"] = datetime.now().isoformat()
        write_counter(counter)
        return {"continue": True}

    write_counter(counter)

    # Remind at 3, 5, and every 3 thereafter
    step_count = counter["count"]

    if step_count == 3:
        return {
            "continue": True,
            "message": (
                "Checkpoint reminder: 3 major edits since last checkpoint. "
                "Consider updating .claude/session-context.md with current goal, "
                "decisions made, files modified, and next steps."
            ),
        }
    elif step_count == 5:
        return {
            "continue": True,
            "message": (
                "Checkpoint due: 5 major edits without a checkpoint. "
                "Please update .claude/session-context.md before continuing. "
                "Required sections: Current goal, Decisions made, Files modified, What's next."
            ),
        }
    elif step_count > 5 and step_count % 3 == 0:
        return {
            "continue": True,
            "message": (
                f"Checkpoint overdue ({step_count} steps). "
                "Update .claude/session-context.md."
            ),
        }

    return {"continue": True}


if __name__ == "__main__":
    print(json.dumps(main()))
