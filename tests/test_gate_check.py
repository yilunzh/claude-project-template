"""Tests for gate-check.py — the feature state machine hook.

Covers:
- Auto-create state file on feature branches
- Advisory suggestions during work
- Code file write enforcement
- Transition gate enforcement (verify needs tests, polish needs passing tests)
- Branch consistency warnings
- Transition logging
- Backward compatibility (no state file = no enforcement)
"""

import json
import os
import sys
from io import StringIO
from unittest.mock import patch

import pytest

# Add hooks lib and hooks dir to path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "_lib")
)
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks")
)

from importlib import import_module

gate_check = import_module("gate-check")


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with .claude/ structure."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    return tmp_path


@pytest.fixture
def state_file(tmp_project):
    """Helper to create a state file with given content."""
    import yaml

    def _create(phase="implement", status="active", branch="feature/test"):
        state = {
            "phase": phase,
            "status": status,
            "branch": branch,
            "created_at": "2026-02-16T10:00:00Z",
            "phase_entered_at": "2026-02-16T10:00:00Z",
            "last_updated": "2026-02-16T10:00:00Z",
            "regressed_from": None,
            "regression_reason": None,
        }
        path = tmp_project / ".claude" / "feature-state.yaml"
        with open(path, "w") as f:
            yaml.dump(state, f, default_flow_style=False, sort_keys=False)
        return state

    return _create


@pytest.fixture
def mock_env(tmp_project):
    """Set up environment for hook testing."""
    env = {
        "CLAUDE_PROJECT_DIR": str(tmp_project),
        "CLAUDE_SESSION_ID": "test-session-unique",
    }
    # Clean up session_once markers
    for name in [
        "gate-check-branch-warn",
        "gate-check-phase-show",
    ]:
        marker = f"/tmp/claude-{name}-test-session-unique"
        if os.path.exists(marker):
            os.remove(marker)
    return env


@pytest.fixture(autouse=True)
def cleanup_session_markers():
    """Clean up session_once markers after each test."""
    yield
    for name in ["gate-check-branch-warn", "gate-check-phase-show"]:
        marker = f"/tmp/claude-{name}-test-session-unique"
        if os.path.exists(marker):
            os.remove(marker)


def _stdin_json(data):
    """Create a stdin mock with JSON data."""
    return StringIO(json.dumps(data))


# ── Auto-create tests (UserPromptSubmit) ────────────────────────────────


class TestAutoCreate:
    """Story 1.1: Auto-create state file on feature branch."""

    def test_creates_on_feature_branch(self, tmp_project, mock_env):
        """First prompt on feature/* branch creates state file."""
        env = {**mock_env, "GATE_CHECK_MODE": "prompt"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(
                gate_check, "get_current_branch",
                return_value="feature/my-feature",
            ),
        ):
            result = gate_check.main()

        assert result["continue"] is True
        assert "phase=clarify" in result.get("message", "")

        state_path = tmp_project / ".claude" / "feature-state.yaml"
        assert state_path.exists()

        import yaml

        with open(state_path) as f:
            state = yaml.safe_load(f)
        assert state["phase"] == "clarify"
        assert state["status"] == "active"
        assert state["branch"] == "feature/my-feature"

    def test_creates_on_fix_branch(self, tmp_project, mock_env):
        """First prompt on fix/* branch also creates state file."""
        env = {**mock_env, "GATE_CHECK_MODE": "prompt"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(
                gate_check, "get_current_branch",
                return_value="fix/bug-123",
            ),
        ):
            gate_check.main()

        state_path = tmp_project / ".claude" / "feature-state.yaml"
        assert state_path.exists()

    def test_skips_on_main(self, tmp_project, mock_env):
        """No state file created on main branch."""
        env = {**mock_env, "GATE_CHECK_MODE": "prompt"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(gate_check, "get_current_branch", return_value="main"),
        ):
            result = gate_check.main()

        assert result["continue"] is True
        state_path = tmp_project / ".claude" / "feature-state.yaml"
        assert not state_path.exists()

    def test_skips_when_file_exists(self, tmp_project, mock_env, state_file):
        """Doesn't overwrite existing state file."""
        state_file(phase="implement")
        env = {**mock_env, "GATE_CHECK_MODE": "prompt"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(
                gate_check, "get_current_branch",
                return_value="feature/test",
            ),
        ):
            result = gate_check.main()

        # Should show current phase, not create new
        assert "phase=clarify" not in result.get("message", "")

        import yaml

        state_path = tmp_project / ".claude" / "feature-state.yaml"
        with open(state_path) as f:
            state = yaml.safe_load(f)
        assert state["phase"] == "implement"  # Not overwritten

    def test_schema_fields_complete(self, tmp_project, mock_env):
        """Created state file has all required v1 schema fields."""
        env = {**mock_env, "GATE_CHECK_MODE": "prompt"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(
                gate_check, "get_current_branch",
                return_value="feature/test",
            ),
        ):
            gate_check.main()

        import yaml

        state_path = tmp_project / ".claude" / "feature-state.yaml"
        with open(state_path) as f:
            state = yaml.safe_load(f)

        required_fields = [
            "phase",
            "status",
            "branch",
            "created_at",
            "phase_entered_at",
            "last_updated",
            "regressed_from",
            "regression_reason",
        ]
        for field in required_fields:
            assert field in state, f"Missing field: {field}"


# ── Branch consistency tests ────────────────────────────────────────────


class TestBranchConsistency:
    """Story 1.5: Branch consistency warning."""

    def test_warns_on_mismatch(self, tmp_project, mock_env, state_file):
        """Warns when state branch differs from current branch."""
        state_file(branch="feature/old-branch")
        env = {**mock_env, "GATE_CHECK_MODE": "prompt"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(
                gate_check, "get_current_branch",
                return_value="feature/new-branch",
            ),
        ):
            result = gate_check.main()

        msg = result.get("message", "")
        assert "feature/old-branch" in msg
        assert "feature/new-branch" in msg

    def test_no_warning_on_match(self, tmp_project, mock_env, state_file):
        """No warning when branches match."""
        state_file(branch="feature/test")
        env = {**mock_env, "GATE_CHECK_MODE": "prompt"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(
                gate_check, "get_current_branch",
                return_value="feature/test",
            ),
        ):
            result = gate_check.main()

        msg = result.get("message", "")
        assert "but you're on" not in msg

    def test_no_warning_without_state(self, tmp_project, mock_env):
        """No warning when no state file exists."""
        env = {**mock_env, "GATE_CHECK_MODE": "prompt"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(gate_check, "get_current_branch", return_value="main"),
        ):
            result = gate_check.main()

        msg = result.get("message", "")
        assert "but you're on" not in msg


# ── Code file enforcement tests (PreToolUse Write|Edit) ─────────────────


class TestCodeFileEnforcement:
    """Story 1.3: Block code file writes during clarify/plan."""

    def test_blocks_py_write_during_clarify(
        self, tmp_project, mock_env, state_file
    ):
        """Block .py file write when phase is clarify."""
        state_file(phase="clarify")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_project / "src" / "main.py"),
                "content": "print('hello')",
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "block"
        assert "clarify" in result["reason"]

    def test_blocks_py_write_during_plan(
        self, tmp_project, mock_env, state_file
    ):
        """Block .py file write when phase is plan."""
        state_file(phase="plan")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_project / "src" / "main.py"),
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "block"

    def test_allows_py_write_during_implement(
        self, tmp_project, mock_env, state_file
    ):
        """Allow .py file write when phase is implement."""
        state_file(phase="implement")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_project / "src" / "main.py"),
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "allow"

    def test_allows_md_write_during_clarify(
        self, tmp_project, mock_env, state_file
    ):
        """Allow .md file write in any phase."""
        state_file(phase="clarify")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_project / "docs" / "notes.md"),
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "allow"

    def test_allows_yaml_write_during_clarify(
        self, tmp_project, mock_env, state_file
    ):
        """Allow .yaml file write in any phase."""
        state_file(phase="clarify")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_project / "config.yaml"),
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "allow"

    def test_allows_claude_dir_files_during_clarify(
        self, tmp_project, mock_env, state_file
    ):
        """Allow files in .claude/ directory in any phase."""
        state_file(phase="clarify")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(
                    tmp_project / ".claude" / "session-context.md"
                ),
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "allow"

    def test_allows_docs_dir_files_during_clarify(
        self, tmp_project, mock_env, state_file
    ):
        """Allow files in docs/ directory in any phase."""
        state_file(phase="clarify")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_project / "docs" / "SPEC.md"),
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "allow"

    def test_no_enforcement_without_state(self, tmp_project, mock_env):
        """No enforcement when state file is missing (backward compatible)."""
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_project / "src" / "main.py"),
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "allow"

    def test_allows_js_write_during_verify(
        self, tmp_project, mock_env, state_file
    ):
        """Allow .js file write during verify (>= implement)."""
        state_file(phase="verify")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_project / "src" / "app.js"),
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "allow"


# ── Transition gate tests ───────────────────────────────────────────────


class TestTransitionGates:
    """Story 1.4: Transition enforcement gates."""

    def test_blocks_verify_without_tests(
        self, tmp_project, mock_env, state_file
    ):
        """Block transition to verify when no test files exist."""
        state_file(phase="implement")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        state_path = str(tmp_project / ".claude" / "feature-state.yaml")
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": state_path,
                "content": "phase: verify\nstatus: active\nbranch: feature/test\n",
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "block"
        assert "test files" in result["reason"].lower()

    def test_allows_verify_with_tests(
        self, tmp_project, mock_env, state_file
    ):
        """Allow transition to verify when test files exist."""
        state_file(phase="implement")
        # Create a test file
        tests_dir = tmp_project / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_something.py").write_text("def test_it(): pass\n")

        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        state_path = str(tmp_project / ".claude" / "feature-state.yaml")
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": state_path,
                "content": "phase: verify\nstatus: active\nbranch: feature/test\n",
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "allow"

    def test_blocks_polish_without_passing_tests(
        self, tmp_project, mock_env, state_file
    ):
        """Block transition to polish when tests haven't passed."""
        state_file(phase="verify")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        state_path = str(tmp_project / ".claude" / "feature-state.yaml")
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": state_path,
                "content": "phase: polish\nstatus: active\nbranch: feature/test\n",
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "block"
        assert "not passing" in result["reason"].lower()

    def test_allows_polish_with_passing_tests(
        self, tmp_project, mock_env, state_file
    ):
        """Allow transition to polish when tests have passed."""
        state_file(phase="verify")
        # Create hook-metrics showing tests passed
        metrics_path = tmp_project / ".claude" / "hook-metrics.jsonl"
        entry = {
            "name": "pre-commit-check",
            "event": "run",
            "decision": "allow",
            "detail": "all checks passed",
        }
        metrics_path.write_text(json.dumps(entry) + "\n")

        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        state_path = str(tmp_project / ".claude" / "feature-state.yaml")
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": state_path,
                "content": "phase: polish\nstatus: active\nbranch: feature/test\n",
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "allow"

    def test_allows_backward_transition(
        self, tmp_project, mock_env, state_file
    ):
        """Backward transitions are always allowed (no gates)."""
        state_file(phase="verify")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        state_path = str(tmp_project / ".claude" / "feature-state.yaml")
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": state_path,
                "content": (
                    "phase: implement\nstatus: active\nbranch: feature/test\n"
                    "regressed_from: verify\n"
                    "regression_reason: found bugs\n"
                ),
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "allow"

    def test_allows_same_phase_write(
        self, tmp_project, mock_env, state_file
    ):
        """Writing same phase (e.g., updating status) is allowed."""
        state_file(phase="implement")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        state_path = str(tmp_project / ".claude" / "feature-state.yaml")
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": state_path,
                "content": "phase: implement\nstatus: blocked\nbranch: feature/test\n",
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "allow"

    def test_edit_transition_detected(
        self, tmp_project, mock_env, state_file
    ):
        """Transition gates also work with Edit tool (not just Write)."""
        state_file(phase="implement")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        state_path = str(tmp_project / ".claude" / "feature-state.yaml")
        stdin_data = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": state_path,
                "old_string": "phase: implement",
                "new_string": "phase: verify",
            },
        }
        # No test files → should block
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["decision"] == "block"


# ── Post-Bash advisory tests ───────────────────────────────────────────


class TestPostBashAdvisory:
    """Story 1.2 (partial): pytest detection and verify suggestion."""

    def test_suggests_verify_on_pytest_during_implement(
        self, tmp_project, mock_env, state_file
    ):
        """Suggest verify when running pytest during implement phase."""
        state_file(phase="implement")
        env = {**mock_env, "GATE_CHECK_MODE": "post_bash"}
        stdin_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -v --tb=short"},
            "tool_result": "3 passed in 1.2s",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["continue"] is True
        assert "verify" in result.get("message", "").lower()

    def test_no_suggestion_during_verify(
        self, tmp_project, mock_env, state_file
    ):
        """No suggestion when already in verify phase."""
        state_file(phase="verify")
        env = {**mock_env, "GATE_CHECK_MODE": "post_bash"}
        stdin_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -v"},
            "tool_result": "5 passed",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["continue"] is True
        assert result.get("message") is None

    def test_no_suggestion_for_non_test_commands(
        self, tmp_project, mock_env, state_file
    ):
        """No suggestion for regular bash commands."""
        state_file(phase="implement")
        env = {**mock_env, "GATE_CHECK_MODE": "post_bash"}
        stdin_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["continue"] is True
        assert result.get("message") is None

    def test_no_suggestion_without_state(self, tmp_project, mock_env):
        """No suggestion when no state file exists."""
        env = {**mock_env, "GATE_CHECK_MODE": "post_bash"}
        stdin_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -v"},
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result["continue"] is True
        assert result.get("message") is None

    def test_logs_test_failure(self, tmp_project, mock_env, state_file):
        """Logs test failure to hook-metrics."""
        state_file(phase="verify")
        env = {**mock_env, "GATE_CHECK_MODE": "post_bash"}
        stdin_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -v"},
            "tool_result": "2 failed, 3 passed in 1.5s",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            gate_check.main()

        metrics_path = tmp_project / ".claude" / "hook-metrics.jsonl"
        assert metrics_path.exists()
        lines = metrics_path.read_text().strip().split("\n")
        last = json.loads(lines[-1])
        assert last["name"] == "gate-check"
        assert last["event"] == "pytest_result"
        assert last["decision"] == "block"

    def test_logs_test_success(self, tmp_project, mock_env, state_file):
        """Logs test success to hook-metrics."""
        state_file(phase="verify")
        env = {**mock_env, "GATE_CHECK_MODE": "post_bash"}
        stdin_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -v"},
            "tool_result": "5 passed in 0.8s",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            gate_check.main()

        metrics_path = tmp_project / ".claude" / "hook-metrics.jsonl"
        lines = metrics_path.read_text().strip().split("\n")
        last = json.loads(lines[-1])
        assert last["name"] == "gate-check"
        assert last["event"] == "pytest_result"
        assert last["decision"] == "allow"

    def test_pip_install_pytest_not_matched(
        self, tmp_project, mock_env, state_file
    ):
        """'pip install pytest' should NOT trigger test detection."""
        state_file(phase="implement")
        env = {**mock_env, "GATE_CHECK_MODE": "post_bash"}
        stdin_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "pip install pytest"},
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            result = gate_check.main()

        assert result.get("message") is None


# ── Transition logging tests ───────────────────────────────────────────


class TestTransitionLogging:
    """Story 1.6: Events logged to hook-metrics.jsonl."""

    def test_auto_create_logged(self, tmp_project, mock_env):
        """Auto-create (idle→clarify) logged to hook-metrics."""
        env = {**mock_env, "GATE_CHECK_MODE": "prompt"}
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(
                gate_check, "get_current_branch",
                return_value="feature/test",
            ),
        ):
            gate_check.main()

        metrics_path = tmp_project / ".claude" / "hook-metrics.jsonl"
        assert metrics_path.exists()
        lines = metrics_path.read_text().strip().split("\n")
        entry = json.loads(lines[-1])
        assert entry["name"] == "gate-check"
        assert entry["event"] == "phase_transition"
        assert "idle -> clarify" in entry.get("detail", "")

    def test_checkpoint_block_logged(
        self, tmp_project, mock_env, state_file
    ):
        """Checkpoint block logged to hook-metrics."""
        state_file(phase="clarify")
        env = {**mock_env, "GATE_CHECK_MODE": "pre_write"}
        stdin_data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_project / "src" / "main.py"),
            },
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("sys.stdin", _stdin_json(stdin_data)),
        ):
            gate_check.main()

        metrics_path = tmp_project / ".claude" / "hook-metrics.jsonl"
        lines = metrics_path.read_text().strip().split("\n")
        entry = json.loads(lines[-1])
        assert entry["name"] == "gate-check"
        assert entry["event"] == "checkpoint_blocked"
        assert entry["decision"] == "block"


# ── Documentation file detection tests ──────────────────────────────────


class TestDocumentationFileDetection:
    """Verify the documentation file allowlist."""

    @pytest.mark.parametrize(
        "filename",
        [
            "README.md",
            "config.yaml",
            "settings.yml",
            "data.json",
            "config.toml",
            "app.cfg",
            "setup.ini",
            "notes.txt",
            "data.csv",
        ],
    )
    def test_doc_extensions_recognized(self, filename):
        assert gate_check.is_documentation_file(f"/project/{filename}") is True

    @pytest.mark.parametrize(
        "filename",
        [
            "main.py",
            "app.js",
            "index.ts",
            "component.tsx",
            "style.css",
            "page.html",
            "lib.go",
            "main.rs",
        ],
    )
    def test_code_extensions_not_doc(self, filename):
        assert gate_check.is_documentation_file(f"/project/{filename}") is False

    def test_claude_dir_is_doc(self):
        assert (
            gate_check.is_documentation_file("/project/.claude/hooks/test.py")
            is True
        )

    def test_docs_dir_is_doc(self):
        assert (
            gate_check.is_documentation_file("/project/docs/architecture.py")
            is True
        )

    def test_dotfiles_are_doc(self):
        """Dotfiles like .gitignore, .editorconfig are config files."""
        assert gate_check.is_documentation_file("/project/.gitignore") is True
        assert gate_check.is_documentation_file("/project/.editorconfig") is True


# ── Integration test — helpers ──────────────────────────────────────────


class TestHelpers:
    """Test helper functions."""

    def test_phase_index_valid(self):
        assert gate_check.phase_index("clarify") == 0
        assert gate_check.phase_index("plan") == 1
        assert gate_check.phase_index("implement") == 2
        assert gate_check.phase_index("verify") == 3
        assert gate_check.phase_index("polish") == 4

    def test_phase_index_invalid(self):
        assert gate_check.phase_index("unknown") == -1
        assert gate_check.phase_index("") == -1

    def test_is_feature_branch(self):
        assert gate_check.is_feature_branch("feature/test") is True
        assert gate_check.is_feature_branch("fix/bug-123") is True
        assert gate_check.is_feature_branch("main") is False
        assert gate_check.is_feature_branch("develop") is False

    def test_test_files_exist(self, tmp_project, mock_env):
        """Detects test files in project."""
        with patch.dict(os.environ, mock_env, clear=False):
            assert gate_check.test_files_exist(str(tmp_project)) is False

            tests_dir = tmp_project / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_something.py").write_text("pass\n")
            assert gate_check.test_files_exist(str(tmp_project)) is True

    def test_last_pytest_passed_no_metrics(self, tmp_project, mock_env):
        """Returns False when no metrics file exists."""
        with patch.dict(os.environ, mock_env, clear=False):
            assert gate_check.last_pytest_passed(str(tmp_project)) is False

    def test_last_pytest_passed_with_passing(self, tmp_project, mock_env):
        """Returns True when last pre-commit-check passed."""
        metrics_path = tmp_project / ".claude" / "hook-metrics.jsonl"
        entries = [
            json.dumps(
                {
                    "name": "pre-commit-check",
                    "event": "run",
                    "decision": "allow",
                }
            ),
        ]
        metrics_path.write_text("\n".join(entries) + "\n")

        with patch.dict(os.environ, mock_env, clear=False):
            assert gate_check.last_pytest_passed(str(tmp_project)) is True

    def test_last_pytest_passed_with_failing(self, tmp_project, mock_env):
        """Returns False when last pre-commit-check failed."""
        metrics_path = tmp_project / ".claude" / "hook-metrics.jsonl"
        entries = [
            json.dumps(
                {
                    "name": "pre-commit-check",
                    "event": "run",
                    "decision": "block",
                }
            ),
        ]
        metrics_path.write_text("\n".join(entries) + "\n")

        with patch.dict(os.environ, mock_env, clear=False):
            assert gate_check.last_pytest_passed(str(tmp_project)) is False

    def test_last_pytest_passed_fallback_suggestion(
        self, tmp_project, mock_env
    ):
        """Returns True when pytest was detected (phase_suggestion) with no failure."""
        metrics_path = tmp_project / ".claude" / "hook-metrics.jsonl"
        entries = [
            json.dumps(
                {
                    "name": "gate-check",
                    "event": "phase_suggestion",
                    "detail": "pytest during implement: pytest -v",
                }
            ),
        ]
        metrics_path.write_text("\n".join(entries) + "\n")

        with patch.dict(os.environ, mock_env, clear=False):
            assert gate_check.last_pytest_passed(str(tmp_project)) is True
