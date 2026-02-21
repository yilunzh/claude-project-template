#!/usr/bin/env python3
"""Advisory Stop hook: memory activity + learning harvest candidates.

Merged from memory-flush.py and harvest-check.py.

Check 1: Any memory YAML modified today? If not, suggest capturing learnings.
Check 2: Any pattern_candidate entries seen today? If yes, suggest /harvest-learnings.

Advisory only — never blocks.
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import check_advisory_compliance, get_project_dir, log_metric


def check_memory_activity():
    """Check if any memory files were modified today."""
    memory_dir = Path(get_project_dir()) / ".claude" / "memory"

    if not memory_dir.exists():
        return False

    today = date.today()

    for subdir in ("corrections", "preferences", "patterns", "reflections"):
        dir_path = memory_dir / subdir
        if not dir_path.exists():
            continue
        for f in dir_path.iterdir():
            if f.is_file():
                try:
                    mtime = date.fromtimestamp(f.stat().st_mtime)
                    if mtime == today:
                        return True
                except OSError:
                    continue

    return False


def find_harvest_candidates():
    """Find pattern_candidate memories with last_seen == today."""
    memory_dir = Path(get_project_dir()) / ".claude" / "memory"

    if not memory_dir.exists() or yaml is None:
        return []

    today = date.today()
    candidates = []

    for subdir_name in ("corrections", "preferences", "patterns"):
        subdir = memory_dir / subdir_name
        if not subdir.exists():
            continue

        for filepath in subdir.iterdir():
            if not filepath.is_file() or filepath.suffix not in (".yaml", ".yml"):
                continue

            try:
                with open(filepath) as f:
                    data = yaml.safe_load(f)

                if not isinstance(data, dict):
                    continue
                if data.get("status") != "pattern_candidate":
                    continue

                last_seen = data.get("last_seen")
                if last_seen is None:
                    continue

                if isinstance(last_seen, date):
                    last_seen_date = last_seen
                elif isinstance(last_seen, str):
                    last_seen_date = date.fromisoformat(last_seen)
                else:
                    continue

                if last_seen_date != today:
                    continue

                candidates.append({
                    "summary": data.get("summary", "(no summary)"),
                    "times_reinforced": data.get("times_reinforced", 0),
                })
            except Exception:
                continue

    candidates.sort(key=lambda c: c["times_reinforced"], reverse=True)
    return candidates[:2]


def check_outcome_tracking():
    """Check if PR activity occurred without track_outcome() calls.

    Scans CLAUDE_TRANSCRIPT for PR merge/revert activity and checks
    whether track_outcome was also called. Returns a reminder message
    if PR activity was found but no outcome tracking.
    """
    transcript = os.environ.get("CLAUDE_TRANSCRIPT", "")
    if not transcript:
        return None

    pr_patterns = ["gh pr merge", "merged pr", "pull request merged", "pr was merged"]
    outcome_pattern = "track_outcome"

    has_pr_activity = any(p in transcript.lower() for p in pr_patterns)
    has_outcome_tracking = outcome_pattern in transcript.lower()

    if has_pr_activity and not has_outcome_tracking:
        return (
            "PR activity detected but no outcome tracking. "
            "Consider calling track_outcome() to record the result "
            "(merged, reverted, etc.) for related memories."
        )

    return None


def main():
    messages = []

    # Check 1: Memory activity today
    if not check_memory_activity():
        messages.append(
            "No memory activity detected this session. "
            "Consider running /reflect before ending to capture "
            "session learnings (corrections, preferences, reflections)."
        )

    # Check 2: Harvest candidates
    candidates = find_harvest_candidates()
    if candidates:
        lines = [
            f'- "{c["summary"]}" ({c["times_reinforced"]}x reinforced)'
            for c in candidates
        ]
        messages.append(
            "Learning candidates detected:\n"
            + "\n".join(lines)
            + "\nConsider running /harvest-learnings to review and promote."
        )

    # Check 3: Outcome tracking reminder
    outcome_msg = check_outcome_tracking()
    if outcome_msg:
        messages.append(outcome_msg)

    # Check 4: Advisory compliance (runs silently, logs results)
    check_advisory_compliance()

    if not messages:
        log_metric("memory-check", "run", "auto", "skip", "no messages")
        return {"continue": True}

    log_metric("memory-check", "run", "auto", "advisory", f"{len(messages)} reminder(s)")
    return {
        "continue": True,
        "message": "\n\n".join(messages),
    }


if __name__ == "__main__":
    print(json.dumps(main()))
