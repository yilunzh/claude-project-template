#!/usr/bin/env python3
"""Auto-format Python files after Edit/Write. Advisory - doesn't block on failure."""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import log_metric


def format_file(file_path):
    """Run black and isort on the file if available."""
    messages = []

    # Check if black is available
    if shutil.which("black"):
        try:
            result = subprocess.run(
                ["black", "--quiet", file_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                messages.append("black")
        except (subprocess.TimeoutExpired, Exception):
            pass

    # Check if isort is available
    if shutil.which("isort"):
        try:
            result = subprocess.run(
                ["isort", "--quiet", file_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                messages.append("isort")
        except (subprocess.TimeoutExpired, Exception):
            pass

    return messages


def main():
    file_path = os.environ.get("CLAUDE_FILE_PATH", "")

    # Only format Python files (not test files to avoid disrupting test structure)
    if not file_path.endswith(".py"):
        log_metric("auto-format", "skip", "auto", "skip", "not a .py file")
        return {"continue": True}

    # Skip hook files themselves to avoid recursion issues
    if ".claude/hooks/" in file_path:
        log_metric("auto-format", "skip", "auto", "skip", "hook file")
        return {"continue": True}

    # Skip if file doesn't exist (might have been deleted)
    if not os.path.exists(file_path):
        log_metric("auto-format", "skip", "auto", "skip", "file not found")
        return {"continue": True}

    formatted_with = format_file(file_path)

    if formatted_with:
        detail = f"formatted with {', '.join(formatted_with)}"
        log_metric("auto-format", "run", "auto", "advisory", detail)
        return {
            "continue": True,
            "message": f"Auto-formatted with {', '.join(formatted_with)}"
        }

    log_metric("auto-format", "run", "auto", "skip", "no formatters applied")
    return {"continue": True}


if __name__ == "__main__":
    print(json.dumps(main()))
