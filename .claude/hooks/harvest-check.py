#!/usr/bin/env python3
"""
Advisory Stop hook: surfaces learning harvest candidates at session end.

Scans memory YAML files for pattern_candidate entries seen today,
sorted by times_reinforced. Suggests running /harvest-learnings if found.

Advisory only -- never blocks.
"""
import json
import os
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def get_project_root():
    """Get project root from environment or walk up."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parent.parent.parent


def find_harvest_candidates():
    """Find pattern_candidate memories with last_seen == today."""
    project_root = get_project_root()
    memory_dir = project_root / ".claude" / "memory"

    if not memory_dir.exists():
        return []

    if yaml is None:
        return []

    today = date.today()

    candidates = []

    for subdir_name in ["corrections", "preferences", "patterns"]:
        subdir = memory_dir / subdir_name
        if not subdir.exists():
            continue

        for filepath in subdir.iterdir():
            if not filepath.is_file() or filepath.suffix not in (".yaml", ".yml"):
                continue

            try:
                with open(filepath, "r") as f:
                    data = yaml.safe_load(f)

                if not isinstance(data, dict):
                    continue

                if data.get("status") != "pattern_candidate":
                    continue

                last_seen = data.get("last_seen")
                if last_seen is None:
                    continue

                # Handle both string "YYYY-MM-DD" and datetime.date object
                if isinstance(last_seen, date):
                    last_seen_date = last_seen
                elif isinstance(last_seen, str):
                    # Parse "YYYY-MM-DD" string (also handles quoted dates from YAML)
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
                # Malformed YAML, missing fields, bad date format -- skip
                continue

    # Sort by times_reinforced descending, take top 2
    candidates.sort(key=lambda c: c["times_reinforced"], reverse=True)
    return candidates[:2]


def main():
    candidates = find_harvest_candidates()

    if not candidates:
        return {"continue": True}

    lines = []
    for c in candidates:
        lines.append(f'- "{c["summary"]}" ({c["times_reinforced"]}x reinforced)')

    message = (
        "Learning candidate detected:\n"
        + "\n".join(lines)
        + "\nConsider running /harvest-learnings to review and promote."
    )

    return {
        "continue": True,
        "message": message,
    }


if __name__ == "__main__":
    print(json.dumps(main()))
