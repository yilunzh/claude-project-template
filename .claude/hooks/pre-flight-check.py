#!/usr/bin/env python3
"""
Advisory UserPromptSubmit hook: validates environment setup on first prompt.
Auto-detects Python/Node projects and checks for common setup issues.
Runs once per session via marker file. Never blocks.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import detect_project_type, log_metric, session_once


def check_python(project_dir):
    """Check Python environment setup."""
    issues = []
    venv_dir = None
    for name in [".venv", "venv"]:
        path = os.path.join(project_dir, name)
        if os.path.isdir(path):
            venv_dir = path
            break

    if not venv_dir:
        issues.append("No virtual environment found (.venv/ or venv/). Create one with: python -m venv .venv")
        return issues

    python_bin = os.path.join(venv_dir, "bin", "python")
    if not os.path.exists(python_bin):
        issues.append(f"Virtual environment at {os.path.basename(venv_dir)}/ exists but has no python binary")
        return issues

    # Check Python version against requires-python
    pyproject_path = os.path.join(project_dir, "pyproject.toml")
    if os.path.exists(pyproject_path):
        try:
            with open(pyproject_path) as f:
                for line in f:
                    if "requires-python" not in line:
                        continue
                    required = line.split("=", 1)[-1].strip().strip('"').strip("'")
                    result = subprocess.run([python_bin, "--version"], capture_output=True, text=True)
                    if result.returncode == 0 and ">=" in required:
                        version = result.stdout.strip().replace("Python ", "")
                        req_ver = required.replace(">=", "").strip()
                        try:
                            if tuple(int(x) for x in version.split(".")[:3]) < tuple(int(x) for x in req_ver.split(".")[:3]):
                                issues.append(f"Python version: {version} (requires-python: {required})")
                        except ValueError:
                            pass
                    break
        except Exception:
            pass

    return issues


def check_node(project_dir):
    """Check Node.js environment setup."""
    if not os.path.isdir(os.path.join(project_dir, "node_modules")):
        return ["node_modules/ not found. Run: npm install"]
    return []


def main():
    if not session_once("pre-flight-done"):
        log_metric("pre-flight-check", "skip", "auto", "skip", "already run this session")
        return {"continue": True}

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")
    project_types = detect_project_type(project_dir)

    if not project_types:
        log_metric("pre-flight-check", "skip", "auto", "skip", "no project type detected")
        return {"continue": True}

    all_issues = []
    if "python" in project_types:
        all_issues.extend(check_python(project_dir))
    if "node" in project_types:
        all_issues.extend(check_node(project_dir))

    if not all_issues:
        log_metric("pre-flight-check", "run", "auto", "allow", f"no issues ({', '.join(project_types)})")
        return {"continue": True}

    issue_list = "\n".join(f"  - {issue}" for issue in all_issues)
    log_metric("pre-flight-check", "run", "auto", "advisory", f"{len(all_issues)} issues found")
    return {
        "continue": True,
        "message": f"Environment check ({', '.join(project_types)} project):\n{issue_list}",
    }


if __name__ == "__main__":
    print(json.dumps(main()))
