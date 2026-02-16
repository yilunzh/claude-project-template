#!/usr/bin/env python3
"""PostToolUse hook: Remind to checkpoint every 3-5 major steps.

Tracks edits via a simple counter file. Advisory only - doesn't block.
Also validates checkpoint sections when session-context.md is written.
(Merged from former checkpoint-validator.py)
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import (
    checkpoint_recent,
    is_major_step,
    log_metric,
    read_json_stdin,
    read_step_counter,
    write_step_counter,
)

CHECKPOINT_SECTIONS = [
    ("current goal", ["current goal", "## current goal", "**current goal**", "# current goal"]),
    ("decisions made", ["decisions made", "## decisions", "**decisions made**", "key decisions"]),
    ("files modified", ["files modified", "## files", "**files modified**", "files touched"]),
    ("what's next", ["what's next", "## next", "**what's next**", "next steps", "remaining"]),
]


def validate_checkpoint(file_path):
    """Validate checkpoint sections when session-context.md is written."""
    if "session-context.md" not in file_path:
        return None

    try:
        with open(file_path, "r") as f:
            content = f.read().lower()
    except IOError:
        return None

    missing = [
        name for name, patterns in CHECKPOINT_SECTIONS
        if not any(p in content for p in patterns)
    ]

    if missing:
        detail = f"missing: {', '.join(missing)}"
        log_metric("checkpoint-reminder", "run", "auto", "advisory", detail)
        return (
            f"Checkpoint incomplete. Missing sections: {', '.join(missing)}. "
            "Required: Current goal, Decisions made, Files modified, What's next."
        )

    # Valid checkpoint — reset step counter
    write_step_counter({
        "count": 0,
        "last_checkpoint": "session-context.md",
        "reset_reason": "valid checkpoint written",
    })
    log_metric("checkpoint-reminder", "run", "auto", "advisory", "validated and reset")
    return None  # No message needed — checkpoint is valid


def main():
    # Read hook input
    input_data = read_json_stdin()
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # If this is a checkpoint write, validate it
    validation_msg = validate_checkpoint(file_path)
    if validation_msg:
        return {"continue": True, "message": validation_msg}
    if "session-context.md" in file_path:
        return {"continue": True}  # Valid checkpoint, no reminder needed

    # Only count major steps
    if not is_major_step(file_path):
        log_metric("checkpoint-reminder", "skip", "auto", "skip", f"not major step: {file_path}")
        return {"continue": True}

    # Read and increment counter
    counter = read_step_counter()
    counter["count"] = counter.get("count", 0) + 1
    counter["last_update"] = datetime.now().isoformat()

    # Check if checkpoint was recently written
    if checkpoint_recent():
        # Reset counter after checkpoint
        counter["count"] = 0
        counter["last_checkpoint"] = datetime.now().isoformat()
        write_step_counter(counter)
        log_metric("checkpoint-reminder", "skip", "auto", "skip", "checkpoint recent")
        return {"continue": True}

    write_step_counter(counter)

    # Remind at 3, 5, and every 3 thereafter
    step_count = counter["count"]

    if step_count == 3:
        log_metric("checkpoint-reminder", "run", "auto", "advisory", "3 steps reached")
        return {
            "continue": True,
            "message": (
                "Checkpoint reminder: 3 major edits since last checkpoint. "
                "Consider updating .claude/session-context.md with current goal, "
                "decisions made, files modified, and next steps."
            ),
        }
    elif step_count == 5:
        log_metric("checkpoint-reminder", "run", "auto", "advisory", "5 steps reached")
        return {
            "continue": True,
            "message": (
                "Checkpoint due: 5 major edits without a checkpoint. "
                "Please update .claude/session-context.md before continuing. "
                "Required sections: Current goal, Decisions made, Files modified, What's next."
            ),
        }
    elif step_count > 5 and step_count % 3 == 0:
        log_metric("checkpoint-reminder", "run", "auto", "advisory", f"{step_count} steps overdue")
        return {
            "continue": True,
            "message": (
                f"Checkpoint overdue ({step_count} steps). "
                "Update .claude/session-context.md."
            ),
        }

    log_metric("checkpoint-reminder", "run", "auto", "allow", f"step {step_count} under threshold")
    return {"continue": True}


if __name__ == "__main__":
    print(json.dumps(main()))
