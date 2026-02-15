"""Tests for self-review-reminder.py advisory hook.

Tests the should_suggest_arch_review() function that detects when
architectural review would be valuable based on:
- New source files created
- Changes spanning multiple directories
- Large files modified
"""

import os
import sys
from unittest.mock import MagicMock, patch

# Add hooks lib and hooks dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "_lib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))

# Import using importlib since the filename has hyphens
from importlib import import_module

reminder = import_module("self-review-reminder")


class TestShouldSuggestArchReview:
    """Tests for should_suggest_arch_review()."""

    @patch.object(reminder, "get_new_source_files")
    @patch.object(reminder, "get_project_dir", return_value="/fake/project")
    def test_new_source_files_trigger(self, mock_dir, mock_new_files):
        """2+ new source files should trigger arch review suggestion."""
        mock_new_files.return_value = ["src/new_module.py", "src/another.py"]
        source_files = ["src/new_module.py", "src/another.py"]

        suggest, reason = reminder.should_suggest_arch_review(source_files)

        assert suggest is True
        assert "2 new source files" in reason

    @patch.object(reminder, "get_new_source_files")
    @patch.object(reminder, "get_project_dir", return_value="/fake/project")
    def test_single_new_file_no_trigger(self, mock_dir, mock_new_files):
        """1 new source file should NOT trigger arch review."""
        mock_new_files.return_value = ["src/new_module.py"]
        source_files = ["src/new_module.py"]

        suggest, _ = reminder.should_suggest_arch_review(source_files)

        assert suggest is False

    @patch.object(reminder, "get_new_source_files")
    @patch.object(reminder, "get_project_dir", return_value="/fake/project")
    def test_three_directories_trigger(self, mock_dir, mock_new_files):
        """Changes spanning 3+ directories should trigger arch review."""
        mock_new_files.return_value = []
        source_files = [
            "src/api/handler.py",
            "src/models/user.py",
            "src/utils/helpers.py",
        ]

        suggest, reason = reminder.should_suggest_arch_review(source_files)

        assert suggest is True
        assert "3 directories" in reason

    @patch.object(reminder, "get_new_source_files")
    @patch.object(reminder, "get_project_dir", return_value="/fake/project")
    def test_two_directories_no_trigger(self, mock_dir, mock_new_files):
        """Changes spanning only 2 directories should NOT trigger."""
        mock_new_files.return_value = []
        source_files = [
            "src/api/handler.py",
            "src/api/routes.py",
            "src/models/user.py",
        ]

        suggest, _ = reminder.should_suggest_arch_review(source_files)

        assert suggest is False

    @patch("builtins.open", create=True)
    @patch("os.path.exists", return_value=True)
    @patch.object(reminder, "get_new_source_files")
    @patch.object(reminder, "get_project_dir", return_value="/fake/project")
    def test_large_file_trigger(self, mock_dir, mock_new_files, mock_exists, mock_open):
        """File over 300 lines should trigger arch review."""
        mock_new_files.return_value = []
        source_files = ["src/big_module.py"]

        # Mock a file with 350 lines
        mock_open.return_value.__enter__ = lambda s: iter(["line\n"] * 350)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        suggest, reason = reminder.should_suggest_arch_review(source_files)

        assert suggest is True
        assert "over 300 lines" in reason

    @patch("os.path.exists", return_value=True)
    @patch.object(reminder, "get_new_source_files")
    @patch.object(reminder, "get_project_dir", return_value="/fake/project")
    def test_small_file_no_trigger(self, mock_dir, mock_new_files, mock_exists):
        """Small file in single directory should NOT trigger."""
        mock_new_files.return_value = []
        source_files = ["src/small.py"]

        # Patch open to return a small file
        import io
        small_content = io.StringIO("line\n" * 50)
        with patch("builtins.open", return_value=small_content):
            suggest, _ = reminder.should_suggest_arch_review(source_files)

        assert suggest is False

    @patch.object(reminder, "get_new_source_files")
    @patch.object(reminder, "get_project_dir", return_value="/fake/project")
    def test_empty_source_files(self, mock_dir, mock_new_files):
        """No source files should not trigger."""
        mock_new_files.return_value = []
        suggest, _ = reminder.should_suggest_arch_review([])
        assert suggest is False


class TestReviewAlreadyRun:
    """Tests for review_already_run()."""

    def test_self_review_detected(self):
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "ran /self-review and found issues"}):
            assert reminder.review_already_run("self-review") is True

    def test_arch_review_detected(self):
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "ran /arch-review, score 8/10"}):
            assert reminder.review_already_run("arch-review") is True

    def test_no_review_in_transcript(self):
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "just editing some files"}):
            assert reminder.review_already_run("self-review") is False

    def test_empty_transcript(self):
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": ""}):
            assert reminder.review_already_run("self-review") is False

    def test_no_transcript_env(self):
        with patch.dict(os.environ, {}, clear=True):
            assert reminder.review_already_run("self-review") is False


class TestMain:
    """Tests for main() output structure."""

    @patch.object(reminder, "get_changed_source_files", return_value=[])
    def test_no_changes_returns_continue(self, mock_files):
        result = reminder.main()
        assert result == {"continue": True}

    @patch.object(reminder, "should_suggest_arch_review", return_value=(False, ""))
    @patch.object(reminder, "review_already_run", return_value=False)
    @patch.object(reminder, "get_changed_source_files", return_value=["a.py", "b.py"])
    def test_few_changes_no_suggestion(self, mock_files, mock_review, mock_arch):
        """Under 5 files and no arch triggers = no suggestion."""
        result = reminder.main()
        assert result == {"continue": True}

    @patch.object(
        reminder, "should_suggest_arch_review",
        return_value=(True, "3 new source files created"),
    )
    @patch.object(reminder, "review_already_run", return_value=False)
    @patch.object(
        reminder,
        "get_changed_source_files",
        return_value=["a.py", "b.py", "c.py", "d.py", "e.py"],
    )
    def test_both_suggestions_shown(self, mock_files, mock_review, mock_arch):
        """5+ files + arch trigger = both suggestions in message."""
        result = reminder.main()
        assert result["continue"] is True
        assert "message" in result
        assert "/self-review" in result["message"]
        assert "/arch-review" in result["message"]

    @patch.object(
        reminder, "should_suggest_arch_review",
        return_value=(True, "changes span 4 directories"),
    )
    @patch.object(reminder, "review_already_run", return_value=False)
    @patch.object(reminder, "get_changed_source_files", return_value=["a.py", "b.py"])
    def test_arch_only_suggestion(self, mock_files, mock_review, mock_arch):
        """Arch trigger without 5+ files = only arch suggestion."""
        result = reminder.main()
        assert result["continue"] is True
        assert "message" in result
        assert "/arch-review" in result["message"]
        assert "/self-review" not in result["message"]
