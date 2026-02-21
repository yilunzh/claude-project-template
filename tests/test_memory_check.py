"""Tests for memory-check.py merged Stop hook."""

import os
import sys
from datetime import date
from unittest.mock import patch

# Add hooks lib and hooks dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "_lib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))

from importlib import import_module

memory_check = import_module("memory-check")


class TestCheckMemoryActivity:
    def test_no_memory_dir(self, tmp_path):
        with patch.object(memory_check, "get_project_dir", return_value=str(tmp_path)):
            assert memory_check.check_memory_activity() is False

    def test_empty_memory_dir(self, tmp_path):
        (tmp_path / ".claude" / "memory").mkdir(parents=True)
        with patch.object(memory_check, "get_project_dir", return_value=str(tmp_path)):
            assert memory_check.check_memory_activity() is False

    def test_file_modified_today(self, tmp_path):
        corrections = tmp_path / ".claude" / "memory" / "corrections"
        corrections.mkdir(parents=True)
        (corrections / "fix.yaml").write_text("test")
        with patch.object(memory_check, "get_project_dir", return_value=str(tmp_path)):
            assert memory_check.check_memory_activity() is True

    def test_file_modified_yesterday(self, tmp_path):
        corrections = tmp_path / ".claude" / "memory" / "corrections"
        corrections.mkdir(parents=True)
        f = corrections / "fix.yaml"
        f.write_text("test")
        # Set mtime to 2 days ago
        import time
        old_time = time.time() - 172800
        os.utime(f, (old_time, old_time))
        with patch.object(memory_check, "get_project_dir", return_value=str(tmp_path)):
            assert memory_check.check_memory_activity() is False


class TestFindHarvestCandidates:
    def test_no_yaml_module(self, tmp_path):
        with (
            patch.object(memory_check, "get_project_dir", return_value=str(tmp_path)),
            patch.object(memory_check, "yaml", None),
        ):
            assert memory_check.find_harvest_candidates() == []

    def test_no_memory_dir(self, tmp_path):
        with patch.object(memory_check, "get_project_dir", return_value=str(tmp_path)):
            assert memory_check.find_harvest_candidates() == []

    def test_finds_candidates(self, tmp_path):
        patterns = tmp_path / ".claude" / "memory" / "patterns"
        patterns.mkdir(parents=True)
        today = date.today().isoformat()
        (patterns / "test.yaml").write_text(
            f"status: pattern_candidate\nlast_seen: '{today}'\n"
            "summary: test pattern\ntimes_reinforced: 3\n"
        )
        with patch.object(memory_check, "get_project_dir", return_value=str(tmp_path)):
            result = memory_check.find_harvest_candidates()
        assert len(result) == 1
        assert result[0]["summary"] == "test pattern"
        assert result[0]["times_reinforced"] == 3

    def test_ignores_non_candidates(self, tmp_path):
        patterns = tmp_path / ".claude" / "memory" / "patterns"
        patterns.mkdir(parents=True)
        (patterns / "active.yaml").write_text(
            "status: active\nsummary: not a candidate\n"
        )
        with patch.object(memory_check, "get_project_dir", return_value=str(tmp_path)):
            assert memory_check.find_harvest_candidates() == []


class TestCheckOutcomeTracking:
    def test_no_transcript(self):
        with patch.dict(os.environ, {}, clear=True):
            assert memory_check.check_outcome_tracking() is None

    def test_pr_activity_no_tracking(self):
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "Then I ran gh pr merge #42"}):
            result = memory_check.check_outcome_tracking()
            assert result is not None
            assert "track_outcome" in result

    def test_pr_activity_with_tracking(self):
        transcript = "I ran gh pr merge #42 and then called track_outcome for the memory"
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": transcript}):
            assert memory_check.check_outcome_tracking() is None

    def test_no_pr_activity(self):
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "Just some regular coding work"}):
            assert memory_check.check_outcome_tracking() is None


class TestMain:
    def test_no_issues_returns_continue(self):
        with (
            patch.object(memory_check, "check_memory_activity", return_value=True),
            patch.object(memory_check, "find_harvest_candidates", return_value=[]),
            patch.object(memory_check, "check_outcome_tracking", return_value=None),
        ):
            result = memory_check.main()
            assert result == {"continue": True}

    def test_no_activity_suggests_reflect(self):
        with (
            patch.object(memory_check, "check_memory_activity", return_value=False),
            patch.object(memory_check, "find_harvest_candidates", return_value=[]),
            patch.object(memory_check, "check_outcome_tracking", return_value=None),
        ):
            result = memory_check.main()
            assert result["continue"] is True
            assert "/reflect" in result["message"]

    def test_harvest_candidates_suggests_harvest(self):
        candidates = [{"summary": "test", "times_reinforced": 2}]
        with (
            patch.object(memory_check, "check_memory_activity", return_value=True),
            patch.object(memory_check, "find_harvest_candidates", return_value=candidates),
            patch.object(memory_check, "check_outcome_tracking", return_value=None),
        ):
            result = memory_check.main()
            assert result["continue"] is True
            assert "/harvest-learnings" in result["message"]

    def test_both_issues_combined(self):
        candidates = [{"summary": "test", "times_reinforced": 1}]
        with (
            patch.object(memory_check, "check_memory_activity", return_value=False),
            patch.object(memory_check, "find_harvest_candidates", return_value=candidates),
            patch.object(memory_check, "check_outcome_tracking", return_value=None),
        ):
            result = memory_check.main()
            assert "/reflect" in result["message"]
            assert "/harvest-learnings" in result["message"]

    def test_outcome_reminder_combined(self):
        with (
            patch.object(memory_check, "check_memory_activity", return_value=True),
            patch.object(memory_check, "find_harvest_candidates", return_value=[]),
            patch.object(
                memory_check, "check_outcome_tracking",
                return_value="PR activity detected but no outcome tracking.",
            ),
        ):
            result = memory_check.main()
            assert result["continue"] is True
            assert "outcome tracking" in result["message"]
