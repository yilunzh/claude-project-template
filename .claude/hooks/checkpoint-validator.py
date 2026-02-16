#!/usr/bin/env python3
"""PostToolUse hook: Validate checkpoint file has required sections.

Triggers after Write to .claude/session-context.md.
Validates required sections exist.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import log_metric, write_step_counter

REQUIRED_SECTIONS = [
    ("current goal", ["current goal", "## current goal", "**current goal**", "# current goal"]),
    (
        "decisions made",
        ["decisions made", "## decisions", "**decisions made**", "key decisions", "# decisions"],
    ),
    (
        "files modified",
        ["files modified", "## files", "**files modified**", "files touched", "# files"],
    ),
    (
        "what's next",
        ["what's next", "## next", "**what's next**", "next steps", "remaining", "# next"],
    ),
]


def validate_checkpoint(content):
    """Check if checkpoint has all required sections."""
    content_lower = content.lower()

    missing = []
    for section_name, patterns in REQUIRED_SECTIONS:
        found = any(pattern in content_lower for pattern in patterns)
        if not found:
            missing.append(section_name)

    return missing


def reset_step_counter():
    """Reset the step counter after a valid checkpoint."""
    try:
        write_step_counter({
            "count": 0,
            "last_checkpoint": "session-context.md",
            "reset_reason": "valid checkpoint written",
        })
    except IOError:
        pass


def main():
    # Read hook input
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return {"continue": True}

    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Only validate session-context.md
    if "session-context.md" not in file_path:
        log_metric("checkpoint-validator", "skip", "auto", "skip", "not session-context.md")
        return {"continue": True}

    # Read the file that was just written
    try:
        with open(file_path, "r") as f:
            content = f.read()
    except IOError:
        log_metric("checkpoint-validator", "skip", "auto", "skip", "cannot read file")
        return {"continue": True}

    # Validate sections
    missing = validate_checkpoint(content)

    if missing:
        detail = f"missing: {', '.join(missing)}"
        log_metric("checkpoint-validator", "run", "auto", "advisory", detail)
        return {
            "continue": True,  # Advisory, don't block
            "message": (
                f"Checkpoint incomplete. Missing sections: {', '.join(missing)}. "
                "Required: Current goal, Decisions made, Files modified, What's next."
            ),
        }

    # Reset step counter on valid checkpoint
    reset_step_counter()

    log_metric("checkpoint-validator", "run", "auto", "advisory", "validated and reset")
    return {"continue": True, "message": "Checkpoint validated. Step counter reset."}


if __name__ == "__main__":
    print(json.dumps(main()))
