#!/usr/bin/env python3
"""After editing, remind to run related tests. Advisory only - doesn't block.

Language-agnostic: Uses shared test runner detection with extension fallback.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import detect_test_runner, log_metric

# Extension-based fallback when detect_test_runner can't find a project runner
_EXTENSION_FALLBACKS = {
    ".py": "pytest",
    ".js": "npm test",
    ".ts": "npm test",
    ".tsx": "npm test",
    ".jsx": "npm test",
    ".rs": "cargo test",
    ".go": "go test ./...",
}


def get_test_reminder(file_path):
    """Generate a test reminder based on detected runner or file extension."""
    # Skip test files themselves
    if "test" in file_path.lower() or "spec" in file_path.lower():
        return None

    # Try project-level detection first
    runner = detect_test_runner()
    if runner:
        return " ".join(runner)

    # Fall back to extension-based suggestion
    ext = os.path.splitext(file_path)[1].lower()
    return _EXTENSION_FALLBACKS.get(ext)


def main():
    file_path = os.environ.get("CLAUDE_FILE_PATH", "")
    test_cmd = get_test_reminder(file_path)

    if test_cmd:
        log_metric("post-edit-verify", "run", "auto", "advisory", f"suggest: {test_cmd}")
        return {
            "continue": True,
            "message": f"Remember to verify changes: {test_cmd}",
        }

    log_metric("post-edit-verify", "run", "auto", "skip", "no test cmd detected")
    return {"continue": True}


if __name__ == "__main__":
    print(json.dumps(main()))
