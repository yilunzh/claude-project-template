"""Regression tests for completion-checklist.py blocking hook.

Tests the transcript parsing logic to ensure:
- Actual test invocations are detected (not install commands)
- Lint tools count as verification
- Failure detection requires test context (not unrelated "failed" mentions)
- Most recent test result wins (pass after fail = OK)
"""

import os
import sys
from unittest.mock import patch

# Add hooks lib to path for the hook to import from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "_lib"))

# Import the hook module directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))
from importlib import import_module

checklist = import_module("completion-checklist")


class TestVerificationDetection:
    """Tests for _check_verification_ran()."""

    def test_pytest_invocation_detected(self):
        transcript = "Running tests...\npytest -v --tb=short\n42 passed"
        assert checklist._check_verification_ran(transcript.lower()) is True

    def test_python_m_pytest_detected(self):
        transcript = "python -m pytest tests/ -v\n42 passed"
        assert checklist._check_verification_ran(transcript.lower()) is True

    def test_npm_test_detected(self):
        transcript = "Verifying...\nnpm test\nAll tests passed"
        assert checklist._check_verification_ran(transcript.lower()) is True

    def test_cargo_test_detected(self):
        transcript = "cargo test\ntest result: ok."
        assert checklist._check_verification_ran(transcript.lower()) is True

    def test_go_test_detected(self):
        transcript = "go test ./...\nok"
        assert checklist._check_verification_ran(transcript.lower()) is True

    def test_pip_install_pytest_not_counted(self):
        """'pip install pytest' should NOT count as running tests."""
        transcript = "pip install pytest\nInstalled successfully"
        assert checklist._check_verification_ran(transcript.lower()) is False

    def test_ruff_check_counts_as_verification(self):
        transcript = "ruff check .\nAll checks passed"
        assert checklist._check_verification_ran(transcript.lower()) is True

    def test_flake8_counts_as_verification(self):
        transcript = "Running flake8\n0 errors found"
        assert checklist._check_verification_ran(transcript.lower()) is True

    def test_eslint_counts_as_verification(self):
        transcript = "npx eslint src/\nNo warnings"
        assert checklist._check_verification_ran(transcript.lower()) is True

    def test_no_verification_detected(self):
        transcript = "I edited some files and wrote code."
        assert checklist._check_verification_ran(transcript.lower()) is False

    def test_mention_of_test_in_prose_not_counted(self):
        """Prose like 'we should test this' shouldn't count."""
        transcript = "We should test this feature before release."
        assert checklist._check_verification_ran(transcript.lower()) is False


class TestFailureDetection:
    """Tests for _check_test_failures()."""

    def test_passing_tests_no_failure(self):
        transcript = "pytest -v\n42 passed in 2.1s"
        assert checklist._check_test_failures(transcript.lower()) is False

    def test_failed_tests_detected(self):
        transcript = "pytest -v\n3 failed, 39 passed"
        assert checklist._check_test_failures(transcript.lower()) is True

    def test_upload_failed_not_counted(self):
        """'upload failed' should NOT trigger failure detection."""
        transcript = "pytest -v\n42 passed\n\nThe upload failed due to network"
        assert checklist._check_test_failures(transcript.lower()) is False

    def test_pass_after_fail_allows(self):
        """If tests pass on retry, session should be allowed."""
        transcript = (
            "pytest -v\n3 failed, 39 passed\n\n"
            "Fixed the issue\n\n"
            "pytest -v\n42 passed in 2.1s"
        )
        assert checklist._check_test_failures(transcript.lower()) is False

    def test_fail_after_pass_blocks(self):
        """If tests fail after previously passing, should block."""
        transcript = (
            "pytest -v\n42 passed\n\n"
            "Made more changes\n\n"
            "pytest -v\n1 failed, 41 passed"
        )
        assert checklist._check_test_failures(transcript.lower()) is True

    def test_no_test_invocation_no_failure(self):
        """No test invocation means no failure check."""
        transcript = "Something failed in the process"
        assert checklist._check_test_failures(transcript.lower()) is False

    def test_zero_failed_is_ok(self):
        transcript = "pytest -v\n0 failed, 42 passed"
        assert checklist._check_test_failures(transcript.lower()) is False


class TestMainFunction:
    """Integration tests for the main() function."""

    def test_no_transcript_allows_with_reminder(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CLAUDE_TRANSCRIPT", None)
            result = checklist.main()
        assert result["continue"] is True
        assert "Reminder" in result.get("message", "")

    def test_tests_ran_and_passed(self):
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "pytest -v\n42 passed"}):
            result = checklist.main()
        assert result["continue"] is True

    def test_no_tests_ran_blocks(self):
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "I edited some files"}):
            result = checklist.main()
        assert result["continue"] is False
        assert "stopReason" in result

    def test_lint_only_allows(self):
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "ruff check .\nAll passed"}):
            result = checklist.main()
        assert result["continue"] is True

    def test_tests_failing_blocks(self):
        with patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": "pytest -v\n3 failed, 39 passed"}):
            result = checklist.main()
        assert result["continue"] is False
        assert "failing" in result.get("stopReason", "").lower()
