#!/usr/bin/env python3
"""Block Edit/Write on main branch for project files.

Enforces feature branch workflow. Allows editing plan files and handoffs.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import get_current_branch, read_json_stdin


def is_exempt_path(file_path):
    """Check if file path is exempt from branch protection."""
    if not file_path:
        return True

    exempt_patterns = [
        "/.claude/plans/",
        "/.claude/handoff.md",
        "/.claude/session-context.md",
        ".claude/CLAUDE.md",
    ]

    for pattern in exempt_patterns:
        if pattern in file_path:
            return True

    # Also exempt user's global claude config
    home = os.path.expanduser("~")
    if file_path.startswith(f"{home}/.claude/"):
        return True

    return False


def main():
    # Read hook input from stdin
    input_data = read_json_stdin()
    if not input_data:
        return {"decision": "allow"}

    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Allow exempt paths (plans, handoffs, global config)
    if is_exempt_path(file_path):
        return {"decision": "allow"}

    # Check branch
    branch = get_current_branch()

    if branch == "main":
        return {
            "decision": "block",
            "reason": (
                f"Cannot edit '{file_path}' on main branch.\n"
                f"Create a feature branch first:\n"
                f"  git checkout -b feature/<name>\n"
                f"Then retry your edit."
            ),
        }

    return {"decision": "allow"}


if __name__ == "__main__":
    print(json.dumps(main()))
