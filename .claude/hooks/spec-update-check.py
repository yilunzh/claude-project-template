#!/usr/bin/env python3
"""
Stop hook to check if SPEC.md documentation update is needed.

Triggers on keyword phrases in the transcript or when all todos complete.
"""
import json
import os
import subprocess
import sys
from glob import glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from hook_utils import log_metric

TRIGGER_PHRASES = [
    "/spec-update",
    "update spec",
    "update documentation",
    "feature complete",
    "update the spec",
    "sync documentation",
]


def read_transcript_tail(transcript_path, lines=50):
    """Read the last N lines of the transcript."""
    try:
        if not transcript_path or not os.path.exists(transcript_path):
            return ""
        with open(transcript_path, "r") as f:
            content = f.readlines()
        return "".join(content[-lines:])
    except Exception:
        return ""


def check_triggers(transcript_content):
    """Check for trigger phrases or all-todos-complete heuristic."""
    content_lower = transcript_content.lower()

    for phrase in TRIGGER_PHRASES:
        if phrase.lower() in content_lower:
            return phrase

    # All-todos-complete heuristic
    all_done = (
        content_lower.count("completed") > 2
        and "pending" not in content_lower
        and "in_progress" not in content_lower
    )
    if all_done:
        return "All todos completed"

    return None


def build_update_prompt(trigger_phrase):
    """Build a prompt for Claude to update SPEC.md."""
    cwd = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    # Get changed files
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=cwd,
        )
        changes = result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        changes = ""

    # Get diff summary
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            capture_output=True, text=True, cwd=cwd,
        )
        diff_summary = result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        diff_summary = ""

    # Find active plan
    plan_excerpt = ""
    plans_dir = os.path.join(cwd, ".claude", "plans")
    if os.path.exists(plans_dir):
        plan_files = glob(os.path.join(plans_dir, "*.md"))
        if plan_files:
            newest = max(plan_files, key=os.path.getmtime)
            try:
                with open(newest, "r") as f:
                    content = f.read()
                plan_excerpt = content[:2000] + "..." if len(content) > 2000 else content
            except Exception:
                pass

    prompt = f"""
---
## Documentation Update Requested

**Trigger**: "{trigger_phrase}"

**Changed Files**:
```
{changes}
```

**Diff Summary**:
```
{diff_summary}
```
"""
    if plan_excerpt:
        prompt += f"""
**Active Plan**:
```markdown
{plan_excerpt}
```
"""
    prompt += """
### Instructions

Please update `docs/SPEC.md` to reflect the changes made:
1. Read the changed files to understand what was implemented
2. Read docs/SPEC.md current state
3. Update sections that no longer match the code, add new features, update structure and status
---
"""
    return prompt


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        hook_input = {}

    transcript_content = read_transcript_tail(hook_input.get("transcript_path", ""))
    trigger = check_triggers(transcript_content)

    if not trigger:
        log_metric("spec-update-check", "skip", "auto", "skip", "not triggered")
        sys.exit(0)

    prompt = build_update_prompt(trigger)
    log_metric("spec-update-check", "run", "auto", "advisory", f"triggered by: {trigger}")
    print(json.dumps({"continue": True, "systemMessage": prompt}))
    sys.exit(0)


if __name__ == "__main__":
    main()
