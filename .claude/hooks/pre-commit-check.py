#!/usr/bin/env python3
"""Block commits if tests/lint fail or committing to main.

Language-agnostic: Auto-detects test runner and linter based on project files.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import (
    detect_linter,
    detect_test_runner,
    get_current_branch,
    log_metric,
    phase_index,
    read_feature_state,
)


def get_staged_file_count():
    """Count total staged files."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], capture_output=True, text=True
    )
    files = [f for f in result.stdout.strip().split("\n") if f]
    return len(files)


def run_command(cmd, name):
    """Run a command and return result."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "name": name,
        "passed": result.returncode == 0,
        "output": (result.stdout + result.stderr)[-1500:],
    }


def check_secrets():
    """Scan staged files for hardcoded secrets."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], capture_output=True, text=True
    )
    staged_files = [f for f in result.stdout.strip().split("\n") if f]

    secret_patterns = [
        (r"AKIA[A-Z0-9]{16}", "AWS Access Key"),
        (r"gh[pors]_[A-Za-z0-9]{36}", "GitHub Token"),
    ]

    findings = []
    for filepath in staged_files:
        if not os.path.exists(filepath):
            continue
        try:
            with open(filepath) as f:
                content = f.read()
        except (IOError, UnicodeDecodeError):
            continue

        for pattern, label in secret_patterns:
            if re.search(pattern, content):
                findings.append(f"{filepath}: potential {label} detected")

    return findings


def main():
    checks = []

    # Check feature phase: block commit if phase < implement
    state = read_feature_state()
    if state is not None:
        phase = state.get("phase", "")
        if phase_index(phase) < phase_index("implement"):
            log_metric(
                "pre-commit-check", "run", "auto", "block",
                f"phase is {phase}",
            )
            return {
                "decision": "block",
                "reason": (
                    f"Phase is `{phase}`. Update to `implement` or later "
                    "before committing.\n"
                    "Edit `.claude/feature-state.yaml` and set "
                    "`phase: implement`."
                ),
            }

    # Check for secrets in staged files
    secret_findings = check_secrets()
    if secret_findings:
        log_metric("pre-commit-check", "run", "auto", "block", "secrets detected")
        return {
            "decision": "block",
            "reason": "Potential secrets detected in staged files:\n"
            + "\n".join(f"  - {f}" for f in secret_findings)
            + "\n\nRemove secrets before committing.",
        }

    # Check branch policy: block ALL commits to main
    branch = get_current_branch()
    file_count = get_staged_file_count()
    if branch == "main" and file_count > 0:
        log_metric("pre-commit-check", "run", "auto", "block", "commit on main")
        return {
            "decision": "block",
            "reason": "Cannot commit directly to main.\n"
            "Create a feature branch: git checkout -b feature/<name>\n"
            "Then open a PR to merge into main.",
        }

    # Detect and run linter
    linter_cmd = detect_linter()
    if linter_cmd:
        checks.append(run_command(linter_cmd, f"Lint ({linter_cmd[0]})"))

    # Detect and run tests
    test_cmd = detect_test_runner()
    if test_cmd:
        checks.append(run_command(test_cmd, f"Tests ({test_cmd[0]})"))
    else:
        # No test runner detected - advisory only
        log_metric("pre-commit-check", "run", "auto", "allow", "no test runner")
        return {
            "decision": "allow",
            "message": "No test runner detected. Consider adding tests."
        }

    failed = [c for c in checks if not c["passed"]]
    if failed:
        reasons = [f"{c['name']}:\n{c['output']}" for c in failed]
        failed_names = ", ".join(c["name"] for c in failed)
        log_metric("pre-commit-check", "run", "auto", "block", f"failed: {failed_names}")
        return {
            "decision": "block",
            "reason": "Pre-commit checks failed:\n\n" + "\n---\n".join(reasons),
        }
    log_metric("pre-commit-check", "run", "auto", "allow", "all checks passed")
    return {"decision": "allow"}


if __name__ == "__main__":
    print(json.dumps(main()))
