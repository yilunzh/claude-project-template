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
