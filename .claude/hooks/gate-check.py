#!/usr/bin/env python3
"""Gate-check hook: manages the feature state machine.

Auto-creates state files on feature branches, suggests phase transitions
during work, and enforces phase consistency at checkpoints.

Registered for multiple hook events via GATE_CHECK_MODE env var:
  prompt    — UserPromptSubmit: auto-create state file + branch consistency
  pre_write — PreToolUse Write|Edit: code file enforcement + transition gates
  post_bash — PostToolUse Bash: pytest detection + result logging
"""
import glob as glob_mod
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import (
    PHASE_ORDER,
    STATE_FILE_REL,
    get_current_branch,
    log_metric,
    phase_index,
    read_feature_state,
    read_json_stdin,
    session_once,
    write_yaml_file,
)

# Documentation file extensions (allowed in any phase)
DOC_EXTENSIONS = frozenset({
    ".md", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".txt", ".csv",
})

# Documentation path prefixes (allowed in any phase)
DOC_PATH_PREFIXES = (".claude/", "docs/")


def get_project_dir():
    return os.environ.get("CLAUDE_PROJECT_DIR", ".")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_feature_branch(branch):
    """Check if branch is a feature or fix branch."""
    return branch.startswith("feature/") or branch.startswith("fix/")


def is_documentation_file(file_path):
    """Check if file is a documentation/config file (allowed in any phase)."""
    if not file_path:
        return True

    # Get relative path
    project_dir = get_project_dir()
    if file_path.startswith(project_dir):
        rel_path = file_path[len(project_dir):].lstrip(os.sep).lstrip("/")
    else:
        rel_path = file_path

    # Normalize separators for matching
    normalized = file_path.replace(os.sep, "/")
    rel_normalized = rel_path.replace(os.sep, "/")

    # Check path prefixes (both relative and absolute forms)
    for prefix in DOC_PATH_PREFIXES:
        if rel_normalized.startswith(prefix) or f"/{prefix}" in normalized:
            return True

    # Check extension
    basename = os.path.basename(file_path)
    _, ext = os.path.splitext(file_path)
    if ext.lower() in DOC_EXTENSIONS:
        return True

    # Dotfiles with no extension (e.g., .gitignore, .editorconfig) are config
    if basename.startswith(".") and not ext:
        return True

    return False


def test_files_exist(project_dir=None):
    """Check if any test files exist in the project."""
    cwd = project_dir or get_project_dir()
    patterns = [
        os.path.join(cwd, "**", "test_*.py"),
        os.path.join(cwd, "**", "*_test.py"),
    ]
    for pattern in patterns:
        matches = glob_mod.glob(pattern, recursive=True)
        real_tests = [
            m for m in matches
            if "__pycache__" not in m and "conftest" not in m
        ]
        if real_tests:
            return True
    return False


def last_pytest_passed(project_dir=None):
    """Check if last test run passed (from hook-metrics.jsonl).

    Checks (in priority order):
    1. pre-commit-check "run" entries (tests+lint ran at commit time)
    2. gate-check "pytest_result" entries (PostToolUse detected pass/fail)
    3. gate-check "phase_suggestion" about pytest with no subsequent failure
       (PostToolUse detected pytest invocation but couldn't read result;
        optimistic — if tests failed the agent would see it)
    """
    cwd = project_dir or get_project_dir()
    metrics_path = os.path.join(cwd, ".claude", "hook-metrics.jsonl")
    if not os.path.exists(metrics_path):
        return False

    try:
        with open(metrics_path) as f:
            lines = f.readlines()
    except IOError:
        return False

    saw_pytest_suggestion = False

    for line in reversed(lines):
        try:
            entry = json.loads(line.strip())
        except json.JSONDecodeError:
            continue

        # pre-commit-check "run" = ran tests+lint; "allow" = all passed
        if entry.get("name") == "pre-commit-check" and entry.get("event") == "run":
            return entry.get("decision") == "allow"

        # gate-check logged pytest result from PostToolUse Bash
        if entry.get("name") == "gate-check" and entry.get("event") == "pytest_result":
            return entry.get("decision") == "allow"

        # gate-check detected pytest invocation (phase_suggestion)
        if (
            entry.get("name") == "gate-check"
            and entry.get("event") == "phase_suggestion"
            and "pytest" in entry.get("detail", "")
        ):
            saw_pytest_suggestion = True

    # Fallback: pytest was invoked and no explicit failure was logged
    return saw_pytest_suggestion


def write_new_state(branch, project_dir=None):
    """Create a new feature state file at clarify phase."""
    cwd = project_dir or get_project_dir()
    path = os.path.join(cwd, STATE_FILE_REL)
    now = now_iso()
    state = {
        "phase": "clarify",
        "status": "active",
        "branch": branch,
        "created_at": now,
        "phase_entered_at": now,
        "last_updated": now,
        "regressed_from": None,
        "regression_reason": None,
    }
    write_yaml_file(path, state)
    return state


# ── Mode: UserPromptSubmit ──────────────────────────────────────────────


def handle_user_prompt():
    """Auto-create state file on feature branch + branch consistency check."""
    project_dir = get_project_dir()
    branch = get_current_branch(project_dir)
    state = read_feature_state(project_dir)
    messages = []

    # Auto-create state file on feature/fix branch
    if is_feature_branch(branch) and state is None:
        state = write_new_state(branch, project_dir)
        log_metric(
            "gate-check", "phase_transition", "auto", "advisory",
            f"idle -> clarify (branch: {branch})",
        )
        messages.append(
            f"Feature state initialized: phase=clarify, branch={branch}"
        )

    if state is None:
        return {"continue": True}

    # Branch consistency check (first prompt per session only)
    if session_once("gate-check-branch-warn"):
        state_branch = state.get("branch", "")
        if state_branch and state_branch != branch:
            log_metric(
                "gate-check", "branch_mismatch", "auto", "advisory",
                f"state={state_branch}, current={branch}",
            )
            messages.append(
                f"State file is for `{state_branch}` but you're on `{branch}`. "
                "Update or recreate state file."
            )

    # Show current phase at session start (first prompt per session only)
    if session_once("gate-check-phase-show"):
        phase = state.get("phase", "unknown")
        status = state.get("status", "active")
        msg = f"Current feature phase: {phase}"
        if status != "active":
            msg += f" (status: {status})"
        messages.append(msg)

    if messages:
        return {"continue": True, "message": "\n".join(messages)}
    return {"continue": True}


# ── Mode: PreToolUse Write|Edit ─────────────────────────────────────────


def handle_pre_write():
    """Code file enforcement + transition gate checks on state file writes."""
    project_dir = get_project_dir()
    state = read_feature_state(project_dir)

    # No state file → no enforcement (backward compatible)
    if state is None:
        return {"decision": "allow"}

    input_data = read_json_stdin()
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Detect writes to the state file itself → transition gate
    if file_path:
        normalized = file_path.replace(os.sep, "/")
        if normalized.endswith(STATE_FILE_REL):
            return _check_transition_gate(input_data, state, project_dir)

    current_phase = state.get("phase", "clarify")
    current_idx = phase_index(current_phase)
    implement_idx = phase_index("implement")

    # Enforcement: block non-doc code writes when phase < implement
    if not is_documentation_file(file_path) and current_idx < implement_idx:
        log_metric(
            "gate-check", "checkpoint_blocked", "auto", "block",
            f"code write during {current_phase}: {os.path.basename(file_path)}",
        )
        return {
            "decision": "block",
            "reason": (
                f"Phase is `{current_phase}`. "
                "Update to `implement` or later before writing code files.\n"
                "Edit `.claude/feature-state.yaml` and set `phase: implement`."
            ),
        }

    return {"decision": "allow"}


def _check_transition_gate(input_data, current_state, project_dir):
    """Check transition gates when writing to feature-state.yaml."""
    tool_input = input_data.get("tool_input", {})
    tool_name = input_data.get("tool_name", "")

    # Extract target phase from content being written
    target_phase = None
    content = ""
    if tool_name == "Write":
        content = tool_input.get("content", "")
    elif tool_name == "Edit":
        content = tool_input.get("new_string", "")

    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("phase:"):
            val = stripped.split(":", 1)[1].strip().strip("'\"")
            if val in PHASE_ORDER:
                target_phase = val
            break

    if target_phase is None:
        return {"decision": "allow"}

    current_phase = current_state.get("phase", "clarify")
    current_idx = phase_index(current_phase)
    target_idx = phase_index(target_phase)

    # Only enforce gates on forward transitions
    if target_idx <= current_idx:
        # Backward transition or same phase — allow
        return {"decision": "allow"}

    # Gate: verify requires test files
    if target_phase == "verify" and not test_files_exist(project_dir):
        log_metric(
            "gate-check", "checkpoint_blocked", "auto", "block",
            "verify transition without test files",
        )
        return {
            "decision": "block",
            "reason": (
                "No test files found. Write tests before entering verify phase.\n"
                "Expected: test_*.py or *_test.py"
            ),
        }

    # Gate: polish requires passing tests
    if target_phase == "polish" and not last_pytest_passed(project_dir):
        log_metric(
            "gate-check", "checkpoint_blocked", "auto", "block",
            "polish transition without passing tests",
        )
        return {
            "decision": "block",
            "reason": (
                "Tests not passing. Fix tests before entering polish phase.\n"
                "Run tests and ensure they pass, then retry."
            ),
        }

    # Log successful forward transition
    log_metric(
        "gate-check", "phase_transition", "auto", "advisory",
        f"{current_phase} -> {target_phase}",
    )

    return {"decision": "allow"}


# ── Mode: PostToolUse Bash ──────────────────────────────────────────────


def handle_post_bash():
    """Detect test runs, log results, and suggest phase transitions."""
    project_dir = get_project_dir()
    state = read_feature_state(project_dir)

    if state is None:
        return {"continue": True}

    input_data = read_json_stdin()
    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")

    # Detect test runner invocation
    test_patterns = [
        r"(?<!install\s)\bpytest\b",
        r"\bnpm\s+test\b",
        r"\bcargo\s+test\b",
        r"\bgo\s+test\b",
    ]
    is_test_run = any(re.search(p, command) for p in test_patterns)

    if not is_test_run:
        return {"continue": True}

    # Log test result if tool_result available
    tool_result = str(input_data.get("tool_result", ""))
    if tool_result:
        result_lower = tool_result.lower()
        if re.search(r"\b[1-9]\d*\s+failed\b", result_lower):
            log_metric(
                "gate-check", "pytest_result", "auto", "block",
                f"test failure: {command[:60]}",
            )
        elif re.search(r"\b\d+\s+passed\b", result_lower):
            log_metric(
                "gate-check", "pytest_result", "auto", "allow",
                f"tests passed: {command[:60]}",
            )

    # Suggest verify phase if currently in implement
    current_phase = state.get("phase", "")
    if current_phase == "implement":
        log_metric(
            "gate-check", "phase_suggestion", "auto", "advisory",
            f"pytest during implement: {command[:60]}",
        )
        return {
            "continue": True,
            "message": (
                "Running tests \u2014 entering verify phase? "
                "Update `.claude/feature-state.yaml` to `phase: verify` if ready."
            ),
        }

    return {"continue": True}


# ── Entrypoint ──────────────────────────────────────────────────────────


def main():
    mode = os.environ.get("GATE_CHECK_MODE", "")

    if mode == "prompt":
        return handle_user_prompt()
    elif mode == "pre_write":
        return handle_pre_write()
    elif mode == "post_bash":
        return handle_post_bash()
    else:
        return {"decision": "allow"}


if __name__ == "__main__":
    print(json.dumps(main()))
