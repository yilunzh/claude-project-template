#!/usr/bin/env python3
"""Prompt agent to verify work before ending session.

This hook runs at Stop and checks if tests/linting were run during the session.
If no verification is detected, it blocks completion.

Uses invocation patterns (tool commands) rather than bare substrings to reduce
false positives from install commands or unrelated mentions.
"""
import json  # noqa: I001
import os
import re


# Patterns that indicate a test runner was actually *invoked* as a tool command.
TEST_INVOCATION_PATTERNS = [
    r"(?<!install )pytest\b",       # pytest (not "pip install pytest")
    r"\bnpm\s+test\b",              # npm test
    r"\bnpx\s+(?:vitest|jest)\b",   # npx vitest / npx jest
    r"\bcargo\s+test\b",            # cargo test
    r"\bgo\s+test\b",               # go test
    r"\bunittest\s+discover\b",     # python -m unittest discover
    r"\bpython.*-m\s+pytest\b",     # python -m pytest
]

# Linting also counts as verification
LINT_INVOCATION_PATTERNS = [
    r"\bruff\s+check\b",
    r"\bflake8\b",
    r"\bnpx\s+eslint\b",
    r"\bcargo\s+clippy\b",
    r"\bgo\s+vet\b",
]

# Combine all verification patterns
ALL_VERIFICATION_PATTERNS = TEST_INVOCATION_PATTERNS + LINT_INVOCATION_PATTERNS


def _check_verification_ran(transcript_lower: str) -> bool:
    """Check if any test or lint tool was actually invoked."""
    return any(
        re.search(pattern, transcript_lower)
        for pattern in ALL_VERIFICATION_PATTERNS
    )


def _check_test_failures(transcript_lower: str) -> bool:
    """Check if the most recent test run has unresolved failures.

    Looks at test result SUMMARY lines (those containing "N passed" or
    "N failed") and checks the last one for a non-zero failure count.
    Only considers lines that appear after a test runner invocation.
    Returns True if tests appear to be failing.
    """
    # Split transcript into blocks (double newline)
    blocks = re.split(r"\n\n+", transcript_lower)

    # Find the last block that contains a test runner invocation
    last_test_block_idx = -1
    for i, block in enumerate(blocks):
        if any(re.search(p, block) for p in TEST_INVOCATION_PATTERNS):
            last_test_block_idx = i

    if last_test_block_idx == -1:
        return False  # No test block found

    # Check blocks from the last test invocation onward
    trailing = "\n\n".join(blocks[last_test_block_idx:])

    # Find test result summary lines: lines with "N passed" and/or "N failed"
    # e.g. "3 failed, 39 passed", "42 passed in 2.1s", "FAILED (failures=3)"
    result_pattern = re.compile(r".*\b\d+\s+(?:passed|failed)\b.*")
    result_lines = result_pattern.findall(trailing)

    if not result_lines:
        # No result lines; check for generic error patterns
        if re.search(r"\bERROR\b", trailing):
            # Check if error is followed by a success indicator
            last_error = list(re.finditer(r"\bERROR\b", trailing))[-1]
            after = trailing[last_error.end():]
            return not bool(re.search(r"\bok\b|\bsuccess", after))
        return False

    # Check the LAST result line for non-zero failure count
    last_result = result_lines[-1]
    fail_match = re.search(r"\b(\d+)\s+failed\b", last_result)

    if fail_match:
        return int(fail_match.group(1)) > 0

    # Last result line has "passed" but no "failed" — tests are OK
    return False


def main():
    # Get transcript from environment (if available)
    transcript = os.environ.get("CLAUDE_TRANSCRIPT", "")

    # If no transcript available, allow but remind
    if not transcript:
        return {
            "continue": True,
            "message": "Reminder: Ensure you ran tests before finishing.",
        }

    transcript_lower = transcript.lower()

    # Check for test/lint invocation patterns
    if not _check_verification_ran(transcript_lower):
        return {
            "continue": False,
            "stopReason": "Tests haven't been run this session. "
            "Run your project's test suite before finishing.",
        }

    # Check for unresolved test failures
    if _check_test_failures(transcript_lower):
        return {
            "continue": False,
            "stopReason": "Tests appear to be failing. "
            "Fix failing tests before finishing.",
        }

    return {"continue": True}


if __name__ == "__main__":
    print(json.dumps(main()))
