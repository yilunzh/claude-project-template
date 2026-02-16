"""Shared utilities for Claude Code hooks.

Consolidates common patterns: git operations, file filtering,
JSON I/O, checkpoint/handoff freshness checks, and metric logging.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


def get_project_dir() -> str:
    """Get project directory from environment."""
    return os.environ.get("CLAUDE_PROJECT_DIR", ".")


def get_current_branch(project_dir: str | None = None) -> str:
    """Get current git branch name.

    Returns empty string on error (detached HEAD, not a git repo, etc.).
    """
    cwd = project_dir or get_project_dir()
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def get_changed_files(
    project_dir: str | None = None,
    staged_only: bool = False,
) -> list[str]:
    """Get changed files from git.

    Args:
        project_dir: Project root directory.
        staged_only: If True, only return staged files. Otherwise staged + unstaged.
    """
    cwd = project_dir or get_project_dir()
    files: set[str] = set()

    try:
        if staged_only:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                cwd=cwd,
            )
            files.update(f for f in result.stdout.strip().split("\n") if f)
        else:
            # Staged
            staged = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                cwd=cwd,
            )
            files.update(f for f in staged.stdout.strip().split("\n") if f)

            # Unstaged
            unstaged = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True,
                text=True,
                cwd=cwd,
            )
            files.update(f for f in unstaged.stdout.strip().split("\n") if f)
    except Exception:
        pass

    return sorted(files)


# ---------- File filtering ----------

# Canonical extension and skip lists, shared across hooks.
CODE_EXTENSIONS = [
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".go", ".rs",
]

SKIP_PATTERNS = [
    "test_",
    "_test.",
    ".test.",
    "tests/",
    "__pycache__",
    ".claude/",
    ".gitignore",
    "README",
    "BRIEF.md",
    "CLAUDE.md",
    "SPEC.md",
    "PATTERNS.md",
    ".json",
    ".toml",
    ".cfg",
    ".ini",
    ".yml",
    ".yaml",
    ".lock",
    ".md",
]

# Additional patterns to skip for step-counting (config/infra files)
STEP_SKIP_PATTERNS = [
    "test_",
    ".spec.",
    ".claude/",
    "requirements",
    "package.json",
    "package-lock.json",
    ".env",
    "session-context.md",
    "handoff.md",
    ".step-counter",
    ".gitignore",
    "pytest.ini",
    "conftest.py",
    "tsconfig.json",
    "vite.config",
    "jest.config",
]


def filter_source_files(files: list[str]) -> list[str]:
    """Filter to source files only (exclude tests, config, .claude/).

    Uses SKIP_PATTERNS — anything matching is excluded.
    """
    return [
        f for f in files
        if not any(pattern in f for pattern in SKIP_PATTERNS)
    ]


def is_code_file(file_path: str) -> bool:
    """Check if file is a code file by extension."""
    return any(file_path.endswith(ext) for ext in CODE_EXTENSIONS)


def is_major_step(file_path: str) -> bool:
    """Determine if an edit to this file constitutes a major step.

    Used by checkpoint-reminder to decide whether to increment counter.
    """
    if any(pattern in file_path for pattern in STEP_SKIP_PATTERNS):
        return False
    return is_code_file(file_path)


# ---------- JSON I/O ----------

def read_json_stdin() -> dict:
    """Read and parse JSON from stdin (hook input).

    Returns empty dict on parse failure or empty input.
    """
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


# ---------- Checkpoint / handoff freshness ----------

def checkpoint_recent(project_dir: str | None = None, minutes: int = 10) -> bool:
    """Check if session-context.md was updated within `minutes`."""
    cwd = project_dir or get_project_dir()
    path = Path(cwd) / ".claude" / "session-context.md"

    if not path.exists():
        return False

    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - mtime < timedelta(minutes=minutes)


def handoff_recent(project_dir: str | None = None, minutes: int = 5) -> bool:
    """Check if handoff.md was updated within `minutes`."""
    cwd = project_dir or get_project_dir()
    path = Path(cwd) / ".claude" / "handoff.md"

    if not path.exists():
        return False

    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - mtime < timedelta(minutes=minutes)


# ---------- Project detection ----------

def detect_project_type(project_dir: str | None = None) -> list[str]:
    """Detect project type(s) from config files.

    Returns a list like ["python"], ["node"], ["python", "node"], etc.
    """
    cwd = project_dir or get_project_dir()
    types = []
    if any(
        os.path.exists(os.path.join(cwd, f))
        for f in ("pyproject.toml", "setup.py", "requirements.txt")
    ):
        types.append("python")
    if os.path.exists(os.path.join(cwd, "package.json")):
        types.append("node")
    if os.path.exists(os.path.join(cwd, "Cargo.toml")):
        types.append("rust")
    if os.path.exists(os.path.join(cwd, "go.mod")):
        types.append("go")
    return types


def _resolve_venv_bin(cmd: str, project_dir: str) -> str:
    """Resolve a command to a venv binary if a venv exists."""
    venv_path = os.path.join(project_dir, ".venv", "bin", cmd)
    if os.path.isfile(venv_path):
        return venv_path
    return cmd


def detect_test_runner(project_dir: str | None = None) -> list[str] | None:
    """Detect test runner command based on project files.

    Returns command list like ["pytest", "-v", "--tb=short", "-q"] or None.
    """
    cwd = project_dir or get_project_dir()

    # Node.js projects
    pkg_json = os.path.join(cwd, "package.json")
    if os.path.exists(pkg_json):
        try:
            with open(pkg_json) as f:
                pkg = json.load(f)
                if "test" in pkg.get("scripts", {}):
                    return ["npm", "test"]
        except (json.JSONDecodeError, IOError):
            pass
        if os.path.exists(os.path.join(cwd, "vitest.config.ts")) or \
           os.path.exists(os.path.join(cwd, "vitest.config.js")):
            return ["npx", "vitest", "run"]
        if os.path.exists(os.path.join(cwd, "jest.config.js")) or \
           os.path.exists(os.path.join(cwd, "jest.config.ts")):
            return ["npx", "jest"]

    # Python projects
    if os.path.exists(os.path.join(cwd, "requirements.txt")) or \
       os.path.exists(os.path.join(cwd, "pyproject.toml")):
        pytest_bin = _resolve_venv_bin("pytest", cwd)
        if os.path.exists(os.path.join(cwd, "pytest.ini")) or \
           os.path.exists(os.path.join(cwd, "conftest.py")):
            return [pytest_bin, "-v", "--tb=short", "-q"]
        pyproject = os.path.join(cwd, "pyproject.toml")
        if os.path.exists(pyproject):
            try:
                with open(pyproject) as f:
                    if "pytest" in f.read():
                        return [pytest_bin, "-v", "--tb=short", "-q"]
            except IOError:
                pass
        python_bin = _resolve_venv_bin("python", cwd)
        return [python_bin, "-m", "unittest", "discover"]

    # Rust projects
    if os.path.exists(os.path.join(cwd, "Cargo.toml")):
        return ["cargo", "test"]

    # Go projects
    if os.path.exists(os.path.join(cwd, "go.mod")):
        return ["go", "test", "./..."]

    return None


def detect_linter(project_dir: str | None = None) -> list[str] | None:
    """Detect linter command based on project files.

    Returns command list like ["ruff", "check", "."] or None.
    """
    cwd = project_dir or get_project_dir()

    # Node.js linters
    eslint_configs = [".eslintrc.js", ".eslintrc.json", "eslint.config.js"]
    if any(os.path.exists(os.path.join(cwd, c)) for c in eslint_configs):
        return ["npx", "eslint", "."]

    # Python linters
    pyproject = os.path.join(cwd, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            with open(pyproject) as f:
                if "ruff" in f.read():
                    return [_resolve_venv_bin("ruff", cwd), "check", "."]
        except IOError:
            pass
    if os.path.exists(os.path.join(cwd, ".flake8")) or \
       os.path.exists(os.path.join(cwd, "setup.cfg")):
        return [_resolve_venv_bin("flake8", cwd)]

    # Rust linter
    if os.path.exists(os.path.join(cwd, "Cargo.toml")):
        return ["cargo", "clippy"]

    # Go linter
    if os.path.exists(os.path.join(cwd, "go.mod")):
        return ["go", "vet", "./..."]

    return None


# ---------- Session-once marker ----------

def session_once(name: str) -> bool:
    """Return True the first time called per session, False after.

    Uses /tmp/ marker files keyed by CLAUDE_SESSION_ID.
    """
    session_id = os.environ.get("CLAUDE_SESSION_ID", "default")
    marker = f"/tmp/claude-{name}-{session_id}"

    if os.path.exists(marker):
        return False

    try:
        with open(marker, "w") as f:
            f.write("done")
    except OSError:
        pass

    return True


# ---------- Step counter ----------

def _step_counter_path(project_dir: str | None = None) -> Path:
    """Get path to step counter file."""
    cwd = project_dir or get_project_dir()
    return Path(cwd) / ".claude" / ".step-counter"


def read_step_counter(project_dir: str | None = None) -> dict:
    """Read current step count and metadata.

    Returns dict with at least {"count": int, "last_checkpoint": ..., "last_update": ...}.
    """
    counter_path = _step_counter_path(project_dir)
    if not counter_path.exists():
        return {"count": 0, "last_checkpoint": None, "last_update": None}

    try:
        with open(counter_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"count": 0, "last_checkpoint": None, "last_update": None}


def write_step_counter(data: dict, project_dir: str | None = None) -> None:
    """Write step counter data."""
    counter_path = _step_counter_path(project_dir)
    counter_path.parent.mkdir(parents=True, exist_ok=True)

    with open(counter_path, "w") as f:
        json.dump(data, f)


# ---------- YAML state file helpers ----------

STATE_FILE_REL = ".claude/feature-state.yaml"

PHASE_ORDER = ["clarify", "plan", "implement", "verify", "polish"]


def read_yaml_file(path: str) -> dict | None:
    """Read a YAML file. Returns dict or None on error/missing."""
    if not os.path.exists(path):
        return None
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


def write_yaml_file(path: str, data: dict) -> None:
    """Write data to a YAML file."""
    import yaml
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def read_feature_state(project_dir: str | None = None) -> dict | None:
    """Read feature state file. Returns dict or None if missing."""
    cwd = project_dir or get_project_dir()
    path = os.path.join(cwd, STATE_FILE_REL)
    return read_yaml_file(path)


def phase_index(phase: str) -> int:
    """Get numeric index for a phase. Returns -1 if unknown."""
    try:
        return PHASE_ORDER.index(phase)
    except ValueError:
        return -1


# ---------- Metrics logging ----------

def log_metric(
    name: str,
    event: str,
    trigger: str = "auto",
    decision: str = "allow",
    detail: str = "",
    project_dir: str | None = None,
) -> None:
    """Append one JSON line to .claude/hook-metrics.jsonl.

    Args:
        name: Hook or command name (e.g. "pre-commit-check").
        event: What happened (e.g. "run", "skip", "compliance").
        trigger: "auto" for hook-triggered, "manual" for user-invoked.
        decision: "allow", "block", "advisory", or "skip".
        detail: Optional extra context.
        project_dir: Project root (defaults to CLAUDE_PROJECT_DIR).
    """
    try:
        cwd = project_dir or get_project_dir()
        metrics_path = Path(cwd) / ".claude" / "hook-metrics.jsonl"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "ts": datetime.now().isoformat(),
            "name": name,
            "event": event,
            "trigger": trigger,
            "decision": decision,
        }
        if detail:
            entry["detail"] = detail

        with open(metrics_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # Fail silent — never break a hook for metrics


# ---------- Advisory compliance checking ----------

# Maps advisory hook names to transcript patterns that indicate compliance.
_COMPLIANCE_PATTERNS: dict[str, list[str]] = {
    "self-review-reminder": ["/self-review", "/arch-review"],
    "checkpoint-reminder": ["session-context.md"],
    "memory-check": [
        "capture_memory", "learning_review", "/harvest-learnings", "/reflect",
    ],
}


def check_advisory_compliance(project_dir: str | None = None) -> list[dict]:
    """Check transcript for evidence that advisory hooks were followed.

    Reads today's advisory metrics from hook-metrics.jsonl, then searches
    CLAUDE_TRANSCRIPT for evidence of compliance.

    Returns list of compliance result dicts (also logged as metrics).
    Reliability: ~65% — good for aggregate trends, not individual instances.
    """
    cwd = project_dir or get_project_dir()
    metrics_path = Path(cwd) / ".claude" / "hook-metrics.jsonl"
    transcript = os.environ.get("CLAUDE_TRANSCRIPT", "")

    if not metrics_path.exists() or not transcript:
        return []

    today = datetime.now().date().isoformat()
    transcript_lower = transcript.lower()

    # Find advisory hooks that fired today
    advisories_fired: set[str] = set()
    try:
        with open(metrics_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    entry.get("decision") == "advisory"
                    and entry.get("ts", "").startswith(today)
                ):
                    advisories_fired.add(entry["name"])
    except OSError:
        return []

    # Check compliance for each advisory that fired
    results = []
    for hook_name in advisories_fired:
        patterns = _COMPLIANCE_PATTERNS.get(hook_name)
        if not patterns:
            continue

        followed = any(p.lower() in transcript_lower for p in patterns)
        decision = "followed" if followed else "ignored"
        result = {"name": hook_name, "decision": decision}
        results.append(result)

        log_metric(
            hook_name, "compliance", "auto", decision,
            project_dir=cwd,
        )

    return results
