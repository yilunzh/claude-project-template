"""Tests for .claude/hooks/lib/hook_utils.py shared utilities."""

import io
import json
import os
import subprocess
import sys
import time
from unittest.mock import patch

# Add hooks lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "_lib"))
import hook_utils


class TestGetCurrentBranch:
    def test_returns_branch_name(self, tmp_path):
        """Normal git repo returns branch name."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "checkout", "-b", "feature/test"],
            cwd=tmp_path,
            capture_output=True,
        )
        assert hook_utils.get_current_branch(str(tmp_path)) == "feature/test"

    def test_returns_main(self, tmp_path):
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, capture_output=True)
        assert hook_utils.get_current_branch(str(tmp_path)) == "main"

    def test_non_git_dir_returns_empty(self, tmp_path):
        """Non-git directory returns empty string."""
        result = hook_utils.get_current_branch(str(tmp_path))
        assert result == ""

    def test_detached_head_returns_empty(self, tmp_path):
        """Detached HEAD returns empty string (git branch --show-current outputs nothing)."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=tmp_path,
            capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@test.com",
                 "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@test.com"},
        )
        rev = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
        ).stdout.strip()
        subprocess.run(["git", "checkout", rev], cwd=tmp_path, capture_output=True)
        assert hook_utils.get_current_branch(str(tmp_path)) == ""


class TestGetChangedFiles:
    def _init_repo(self, tmp_path):
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@test.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@test.com",
        }
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=tmp_path, capture_output=True, env=env,
        )
        return env

    def test_staged_files(self, tmp_path):
        self._init_repo(tmp_path)
        (tmp_path / "a.py").write_text("x")
        subprocess.run(["git", "add", "a.py"], cwd=tmp_path, capture_output=True)
        files = hook_utils.get_changed_files(str(tmp_path), staged_only=True)
        assert "a.py" in files

    def test_unstaged_files(self, tmp_path):
        env = self._init_repo(tmp_path)
        (tmp_path / "b.py").write_text("x")
        subprocess.run(["git", "add", "b.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add b"], cwd=tmp_path, capture_output=True, env=env,
        )
        (tmp_path / "b.py").write_text("modified")
        files = hook_utils.get_changed_files(str(tmp_path), staged_only=False)
        assert "b.py" in files

    def test_staged_only_excludes_unstaged(self, tmp_path):
        env = self._init_repo(tmp_path)
        (tmp_path / "a.py").write_text("x")
        subprocess.run(["git", "add", "a.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add a"], cwd=tmp_path, capture_output=True, env=env,
        )
        (tmp_path / "a.py").write_text("modified")
        # a.py is unstaged
        (tmp_path / "b.py").write_text("y")
        subprocess.run(["git", "add", "b.py"], cwd=tmp_path, capture_output=True)
        # b.py is staged
        staged = hook_utils.get_changed_files(str(tmp_path), staged_only=True)
        assert "b.py" in staged
        assert "a.py" not in staged

    def test_non_git_dir_returns_empty(self, tmp_path):
        assert hook_utils.get_changed_files(str(tmp_path)) == []


class TestFilterSourceFiles:
    def test_includes_python_files(self):
        files = ["src/main.py", "lib/utils.js", "app.ts"]
        result = hook_utils.filter_source_files(files)
        assert "src/main.py" in result
        assert "lib/utils.js" in result
        assert "app.ts" in result

    def test_excludes_test_files(self):
        files = ["test_main.py", "src/main_test.py", "src/main.test.js", "tests/conftest.py"]
        result = hook_utils.filter_source_files(files)
        assert len(result) == 0

    def test_excludes_claude_dir(self):
        files = [".claude/hooks/branch-check.py", "src/app.py"]
        result = hook_utils.filter_source_files(files)
        assert result == ["src/app.py"]

    def test_excludes_config_files(self):
        files = ["package.json", "pyproject.toml", "config.yaml", "deps.lock"]
        result = hook_utils.filter_source_files(files)
        assert len(result) == 0

    def test_excludes_markdown(self):
        files = ["README.md", "CLAUDE.md", "BRIEF.md", "docs/notes.md"]
        result = hook_utils.filter_source_files(files)
        assert len(result) == 0


class TestIsCodeFile:
    def test_python_file(self):
        assert hook_utils.is_code_file("src/main.py") is True

    def test_javascript_file(self):
        assert hook_utils.is_code_file("app.js") is True

    def test_typescript_file(self):
        assert hook_utils.is_code_file("component.tsx") is True

    def test_html_file(self):
        assert hook_utils.is_code_file("index.html") is True

    def test_go_file(self):
        assert hook_utils.is_code_file("main.go") is True

    def test_rust_file(self):
        assert hook_utils.is_code_file("lib.rs") is True

    def test_not_code_json(self):
        assert hook_utils.is_code_file("data.json") is False

    def test_not_code_yaml(self):
        assert hook_utils.is_code_file("config.yaml") is False

    def test_not_code_markdown(self):
        assert hook_utils.is_code_file("README.md") is False

    def test_not_code_pyc(self):
        assert hook_utils.is_code_file("cache.pyc") is False

    def test_not_code_no_extension(self):
        assert hook_utils.is_code_file("Makefile") is False

    def test_not_code_empty(self):
        assert hook_utils.is_code_file("") is False


class TestIsMajorStep:
    def test_python_source_file(self):
        assert hook_utils.is_major_step("src/main.py") is True

    def test_test_file_excluded(self):
        assert hook_utils.is_major_step("test_main.py") is False

    def test_claude_dir_excluded(self):
        assert hook_utils.is_major_step(".claude/hooks/check.py") is False

    def test_config_excluded(self):
        assert hook_utils.is_major_step("package.json") is False

    def test_session_context_excluded(self):
        assert hook_utils.is_major_step("session-context.md") is False

    def test_handoff_excluded(self):
        assert hook_utils.is_major_step("handoff.md") is False

    def test_conftest_excluded(self):
        assert hook_utils.is_major_step("conftest.py") is False

    def test_non_code_not_major(self):
        assert hook_utils.is_major_step("README.md") is False


class TestReadJsonStdin:
    def test_valid_json(self):
        data = {"tool_input": {"file_path": "src/foo.py"}}
        with patch("sys.stdin", io.StringIO(json.dumps(data))):
            result = hook_utils.read_json_stdin()
        assert result == data

    def test_malformed_json(self):
        with patch("sys.stdin", io.StringIO("{invalid json")):
            result = hook_utils.read_json_stdin()
        assert result == {}

    def test_empty_input(self):
        with patch("sys.stdin", io.StringIO("")):
            result = hook_utils.read_json_stdin()
        assert result == {}


class TestCheckpointRecent:
    def test_no_file_returns_false(self, tmp_path):
        assert hook_utils.checkpoint_recent(str(tmp_path)) is False

    def test_recent_file_returns_true(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        ctx = claude_dir / "session-context.md"
        ctx.write_text("## Current Goal\nTest")
        assert hook_utils.checkpoint_recent(str(tmp_path)) is True

    def test_stale_file_returns_false(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        ctx = claude_dir / "session-context.md"
        ctx.write_text("## Current Goal\nTest")
        # Set mtime to 15 minutes ago
        old_time = time.time() - 900
        os.utime(ctx, (old_time, old_time))
        assert hook_utils.checkpoint_recent(str(tmp_path)) is False


class TestHandoffRecent:
    def test_no_file_returns_false(self, tmp_path):
        assert hook_utils.handoff_recent(str(tmp_path)) is False

    def test_recent_file_returns_true(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        ho = claude_dir / "handoff.md"
        ho.write_text("## What we were doing\nTest")
        assert hook_utils.handoff_recent(str(tmp_path)) is True

    def test_stale_file_returns_false(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        ho = claude_dir / "handoff.md"
        ho.write_text("## What we were doing\nTest")
        old_time = time.time() - 600  # 10 minutes ago, threshold is 5
        os.utime(ho, (old_time, old_time))
        assert hook_utils.handoff_recent(str(tmp_path)) is False


class TestDetectProjectType:
    def test_python_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]")
        assert hook_utils.detect_project_type(str(tmp_path)) == ["python"]

    def test_python_setup_py(self, tmp_path):
        (tmp_path / "setup.py").write_text("setup()")
        assert hook_utils.detect_project_type(str(tmp_path)) == ["python"]

    def test_python_requirements(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask")
        assert hook_utils.detect_project_type(str(tmp_path)) == ["python"]

    def test_node_project(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        assert hook_utils.detect_project_type(str(tmp_path)) == ["node"]

    def test_rust_project(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]")
        assert hook_utils.detect_project_type(str(tmp_path)) == ["rust"]

    def test_go_project(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example")
        assert hook_utils.detect_project_type(str(tmp_path)) == ["go"]

    def test_multi_type(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "package.json").write_text("{}")
        result = hook_utils.detect_project_type(str(tmp_path))
        assert "python" in result
        assert "node" in result

    def test_empty_dir(self, tmp_path):
        assert hook_utils.detect_project_type(str(tmp_path)) == []


class TestDetectTestRunner:
    def test_npm_test_script(self, tmp_path):
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest"}})
        )
        assert hook_utils.detect_test_runner(str(tmp_path)) == ["npm", "test"]

    def test_vitest(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}))
        (tmp_path / "vitest.config.ts").write_text("")
        assert hook_utils.detect_test_runner(str(tmp_path)) == [
            "npx", "vitest", "run",
        ]

    def test_jest(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {}}))
        (tmp_path / "jest.config.js").write_text("")
        assert hook_utils.detect_test_runner(str(tmp_path)) == ["npx", "jest"]

    def test_pytest_via_ini(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "pytest.ini").write_text("[pytest]")
        result = hook_utils.detect_test_runner(str(tmp_path))
        assert result[0] == "pytest"

    def test_pytest_via_conftest(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("pytest")
        (tmp_path / "conftest.py").write_text("")
        result = hook_utils.detect_test_runner(str(tmp_path))
        assert result[0] == "pytest"

    def test_pytest_via_pyproject_content(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]")
        result = hook_utils.detect_test_runner(str(tmp_path))
        assert result[0] == "pytest"

    def test_python_fallback_unittest(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask")
        result = hook_utils.detect_test_runner(str(tmp_path))
        assert result == ["python", "-m", "unittest", "discover"]

    def test_cargo(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]")
        assert hook_utils.detect_test_runner(str(tmp_path)) == ["cargo", "test"]

    def test_go(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example")
        assert hook_utils.detect_test_runner(str(tmp_path)) == [
            "go", "test", "./...",
        ]

    def test_no_project(self, tmp_path):
        assert hook_utils.detect_test_runner(str(tmp_path)) is None


class TestDetectLinter:
    def test_ruff(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]")
        assert hook_utils.detect_linter(str(tmp_path)) == ["ruff", "check", "."]

    def test_flake8(self, tmp_path):
        (tmp_path / ".flake8").write_text("[flake8]")
        assert hook_utils.detect_linter(str(tmp_path)) == ["flake8"]

    def test_eslint(self, tmp_path):
        (tmp_path / ".eslintrc.json").write_text("{}")
        assert hook_utils.detect_linter(str(tmp_path)) == ["npx", "eslint", "."]

    def test_cargo_clippy(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]")
        assert hook_utils.detect_linter(str(tmp_path)) == ["cargo", "clippy"]

    def test_go_vet(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example")
        assert hook_utils.detect_linter(str(tmp_path)) == ["go", "vet", "./..."]

    def test_no_linter(self, tmp_path):
        assert hook_utils.detect_linter(str(tmp_path)) is None


class TestSessionOnce:
    def test_first_call_returns_true(self):
        name = f"test-session-once-{os.getpid()}"
        marker = f"/tmp/claude-{name}-default"
        # Clean up any leftover marker
        if os.path.exists(marker):
            os.remove(marker)
        try:
            with patch.dict(os.environ, {"CLAUDE_SESSION_ID": "default"}):
                assert hook_utils.session_once(name) is True
        finally:
            if os.path.exists(marker):
                os.remove(marker)

    def test_second_call_returns_false(self):
        name = f"test-session-once-repeat-{os.getpid()}"
        marker = f"/tmp/claude-{name}-default"
        if os.path.exists(marker):
            os.remove(marker)
        try:
            with patch.dict(os.environ, {"CLAUDE_SESSION_ID": "default"}):
                hook_utils.session_once(name)
                assert hook_utils.session_once(name) is False
        finally:
            if os.path.exists(marker):
                os.remove(marker)

    def test_different_sessions_independent(self):
        name = f"test-session-once-diff-{os.getpid()}"
        markers = [
            f"/tmp/claude-{name}-sess1",
            f"/tmp/claude-{name}-sess2",
        ]
        for m in markers:
            if os.path.exists(m):
                os.remove(m)
        try:
            with patch.dict(os.environ, {"CLAUDE_SESSION_ID": "sess1"}):
                assert hook_utils.session_once(name) is True
            with patch.dict(os.environ, {"CLAUDE_SESSION_ID": "sess2"}):
                assert hook_utils.session_once(name) is True
        finally:
            for m in markers:
                if os.path.exists(m):
                    os.remove(m)


class TestReadStepCounter:
    def test_no_file_returns_defaults(self, tmp_path):
        result = hook_utils.read_step_counter(str(tmp_path))
        assert result == {"count": 0, "last_checkpoint": None, "last_update": None}

    def test_reads_existing_counter(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        counter = claude_dir / ".step-counter"
        data = {"count": 5, "last_checkpoint": "2025-01-01", "last_update": "2025-01-01"}
        counter.write_text(json.dumps(data))
        result = hook_utils.read_step_counter(str(tmp_path))
        assert result["count"] == 5

    def test_malformed_json_returns_defaults(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        counter = claude_dir / ".step-counter"
        counter.write_text("{bad json")
        result = hook_utils.read_step_counter(str(tmp_path))
        assert result["count"] == 0


class TestLogMetric:
    def test_writes_jsonl_entry(self, tmp_path):
        hook_utils.log_metric("test-hook", "run", "auto", "allow", project_dir=str(tmp_path))
        metrics_path = tmp_path / ".claude" / "hook-metrics.jsonl"
        assert metrics_path.exists()
        entry = json.loads(metrics_path.read_text().strip())
        assert entry["name"] == "test-hook"
        assert entry["event"] == "run"
        assert entry["trigger"] == "auto"
        assert entry["decision"] == "allow"
        assert "ts" in entry
        assert "detail" not in entry  # No detail when empty

    def test_includes_detail_when_provided(self, tmp_path):
        hook_utils.log_metric("test", "run", detail="extra info", project_dir=str(tmp_path))
        metrics_path = tmp_path / ".claude" / "hook-metrics.jsonl"
        entry = json.loads(metrics_path.read_text().strip())
        assert entry["detail"] == "extra info"

    def test_appends_multiple_entries(self, tmp_path):
        hook_utils.log_metric("hook1", "run", project_dir=str(tmp_path))
        hook_utils.log_metric("hook2", "skip", project_dir=str(tmp_path))
        metrics_path = tmp_path / ".claude" / "hook-metrics.jsonl"
        lines = metrics_path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["name"] == "hook1"
        assert json.loads(lines[1])["name"] == "hook2"

    def test_creates_parent_dirs(self, tmp_path):
        hook_utils.log_metric("test", "run", project_dir=str(tmp_path))
        assert (tmp_path / ".claude" / "hook-metrics.jsonl").exists()

    def test_silent_on_error(self):
        # Writing to a non-existent dir that can't be created should not raise
        hook_utils.log_metric("test", "run", project_dir="/nonexistent/path/xyz")


class TestCheckAdvisoryCompliance:
    def test_no_metrics_file(self, tmp_path):
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "pytest ran fine"}):
            result = hook_utils.check_advisory_compliance(str(tmp_path))
        assert result == []

    def test_no_transcript(self, tmp_path):
        metrics = tmp_path / ".claude" / "hook-metrics.jsonl"
        metrics.parent.mkdir(parents=True)
        metrics.write_text('{"name":"post-edit-verify","event":"run","decision":"advisory","ts":"2026-02-15T10:00:00"}\n')
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": ""}, clear=False):
            result = hook_utils.check_advisory_compliance(str(tmp_path))
        assert result == []

    def test_detects_followed(self, tmp_path):
        today = hook_utils.datetime.now().date().isoformat()
        metrics = tmp_path / ".claude" / "hook-metrics.jsonl"
        metrics.parent.mkdir(parents=True)
        entry = json.dumps({
            "name": "self-review-reminder", "event": "run",
            "decision": "advisory", "ts": f"{today}T10:00:00",
        })
        metrics.write_text(entry + "\n")
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "ran /self-review"}):
            result = hook_utils.check_advisory_compliance(str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "self-review-reminder"
        assert result[0]["decision"] == "followed"

    def test_detects_ignored(self, tmp_path):
        today = hook_utils.datetime.now().date().isoformat()
        metrics = tmp_path / ".claude" / "hook-metrics.jsonl"
        metrics.parent.mkdir(parents=True)
        entry = json.dumps({
            "name": "self-review-reminder", "event": "run",
            "decision": "advisory", "ts": f"{today}T10:00:00",
        })
        metrics.write_text(entry + "\n")
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "just editing"}):
            result = hook_utils.check_advisory_compliance(str(tmp_path))
        assert len(result) == 1
        assert result[0]["decision"] == "ignored"

    def test_skips_non_advisory(self, tmp_path):
        today = hook_utils.datetime.now().date().isoformat()
        metrics = tmp_path / ".claude" / "hook-metrics.jsonl"
        metrics.parent.mkdir(parents=True)
        entry = json.dumps({
            "name": "branch-check", "event": "run",
            "decision": "allow", "ts": f"{today}T10:00:00",
        })
        metrics.write_text(entry + "\n")
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "some work"}):
            result = hook_utils.check_advisory_compliance(str(tmp_path))
        assert result == []


class TestWriteStepCounter:
    def test_writes_counter(self, tmp_path):
        data = {"count": 3, "last_checkpoint": None, "last_update": "now"}
        hook_utils.write_step_counter(data, str(tmp_path))
        counter = tmp_path / ".claude" / ".step-counter"
        assert counter.exists()
        written = json.loads(counter.read_text())
        assert written["count"] == 3

    def test_creates_parent_dirs(self, tmp_path):
        data = {"count": 1}
        hook_utils.write_step_counter(data, str(tmp_path))
        assert (tmp_path / ".claude" / ".step-counter").exists()

    def test_overwrites_existing(self, tmp_path):
        hook_utils.write_step_counter({"count": 1}, str(tmp_path))
        hook_utils.write_step_counter({"count": 10}, str(tmp_path))
        counter = tmp_path / ".claude" / ".step-counter"
        assert json.loads(counter.read_text())["count"] == 10
