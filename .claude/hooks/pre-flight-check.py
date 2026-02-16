#!/usr/bin/env python3
"""
Advisory UserPromptSubmit hook: validates environment setup on first prompt.
Auto-detects project type (Python/Node) and checks for common setup issues.
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

    # Check for virtual environment
    venv_paths = [
        os.path.join(project_dir, ".venv"),
        os.path.join(project_dir, "venv"),
    ]
    venv_found = any(os.path.isdir(p) for p in venv_paths)
    if not venv_found:
        issues.append(
            "No virtual environment found (.venv/ or venv/). "
            "Create one with: python -m venv .venv"
        )
        return issues  # Can't check further without venv

    # Find the active venv
    venv_dir = next(p for p in venv_paths if os.path.isdir(p))
    python_bin = os.path.join(venv_dir, "bin", "python")

    if not os.path.exists(python_bin):
        issues.append(
            f"Virtual environment at {os.path.basename(venv_dir)}/ "
            "exists but has no python binary"
        )
        return issues

    # Check Python version against requires-python in pyproject.toml
    pyproject_path = os.path.join(project_dir, "pyproject.toml")
    if os.path.exists(pyproject_path):
        try:
            with open(pyproject_path) as f:
                content = f.read()
            # Simple parse for requires-python
            for line in content.split("\n"):
                if "requires-python" in line:
                    required = line.split("=", 1)[-1].strip().strip('"').strip("'")
                    result = subprocess.run(
                        [python_bin, "--version"],
                        capture_output=True, text=True,
                    )
                    if result.returncode == 0:
                        version = result.stdout.strip().replace("Python ", "")
                        # Compare version tuples for correct numeric ordering
                        if ">=" in required:
                            req_ver = required.replace(">=", "").strip()
                            try:
                                ver_tuple = tuple(int(x) for x in version.split(".")[:3])
                                req_tuple = tuple(int(x) for x in req_ver.split(".")[:3])
                                if ver_tuple < req_tuple:
                                    issues.append(
                                        f"Python version: {version} "
                                        f"(requires-python: {required}). "
                                        "Verify compatibility if you "
                                        "see import errors."
                                    )
                            except ValueError:
                                pass
                        else:
                            issues.append(
                                f"Python version: {version} "
                                f"(requires-python: {required}). "
                                "Verify compatibility if you "
                                "see import errors."
                            )
                    break
        except Exception:
            pass

    # Check if key dependencies are installed
    req_files = ["requirements.txt", "requirements-dev.txt"]
    for req_file in req_files:
        req_path = os.path.join(project_dir, req_file)
        if os.path.exists(req_path):
            result = subprocess.run(
                [python_bin, "-m", "pip", "list", "--format=columns"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                installed = result.stdout.lower()
                with open(req_path) as f:
                    for line in f:
                        pkg = (
                            line.strip()
                            .split("==")[0]
                            .split(">=")[0]
                            .split("~=")[0]
                            .strip()
                            .lower()
                        )
                        if pkg and not pkg.startswith("#") and not pkg.startswith("-"):
                            if pkg.replace("-", "_") not in installed.replace("-", "_"):
                                issues.append(
                                    f"Package '{pkg}' from {req_file} may not be installed. "
                                    f"Run: {venv_dir}/bin/pip install -r {req_file}"
                                )
                                break  # One warning is enough
            break

    return issues


def check_node(project_dir):
    """Check Node.js environment setup."""
    issues = []

    # Check for node_modules
    if not os.path.isdir(os.path.join(project_dir, "node_modules")):
        issues.append("node_modules/ not found. Run: npm install")
        return issues

    # Check Node version against engines in package.json
    pkg_path = os.path.join(project_dir, "package.json")
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path) as f:
                import json as j
                pkg = j.load(f)
            engines = pkg.get("engines", {})
            if "node" in engines:
                result = subprocess.run(
                    ["node", "--version"],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    version = result.stdout.strip()
                    required = engines["node"]
                    # Informational only
                    issues.append(
                        f"Node version: {version} (engines.node: {required}). "
                        "Verify compatibility if you see module errors."
                    ) if version else None
        except Exception:
            pass

    return issues


def main():
    # Only run once per session
    if not session_once("pre-flight-done"):
        log_metric("pre-flight-check", "skip", "auto", "skip", "already run this session")
        return {"continue": True}

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")

    project_types = detect_project_type(project_dir)

    if not project_types:
        log_metric("pre-flight-check", "skip", "auto", "skip", "no project type detected")
        return {"continue": True}  # Can't detect project type, skip silently

    all_issues = []

    if "python" in project_types:
        all_issues.extend(check_python(project_dir))
    if "node" in project_types:
        all_issues.extend(check_node(project_dir))

    if not all_issues:
        detail = f"no issues ({', '.join(project_types)})"
        log_metric("pre-flight-check", "run", "auto", "allow", detail)
        return {"continue": True}

    issue_list = "\n".join(f"  - {issue}" for issue in all_issues)
    log_metric("pre-flight-check", "run", "auto", "advisory", f"{len(all_issues)} issues found")
    return {
        "continue": True,
        "message": f"Environment check ({', '.join(project_types)} project):\n{issue_list}",
    }


if __name__ == "__main__":
    print(json.dumps(main()))
