---
description: Capture session reflection and learnings to memory
---

# Session Reflection

First, log this invocation: `.venv/bin/python3 .claude/hooks/_lib/log_command.py "reflect"`

Run the full reflect workflow. All steps are mandatory — do not skip any.

## Step 1: Review conversation for uncaptured learnings

Scan the entire conversation for:
- Corrections the user made (wrong assumptions, incorrect outputs)
- Preferences the user stated (workflow, formatting, tooling)
- Patterns observed (approaches that worked well or poorly)

For each uncaptured learning, call `capture_memory()` with the appropriate type, scope, and signal. Use this command pattern:

```bash
PYTHONPATH=src .venv/bin/python3 -c "
from memory_mcp.tools.memory import capture_memory
print(capture_memory(type='<type>', summary='<summary>', scope='<scope>', signal='<signal>'))
"
```

If all learnings were already captured, state that explicitly and move on.

## Step 2: Capture session reflection

Call `capture_reflection()` with a structured summary of the session. This is MANDATORY even if individual learnings were already captured — reflections serve as session-level narrative for post-hoc review.

```bash
PYTHONPATH=src .venv/bin/python3 -c "
from memory_mcp.tools.memory import capture_reflection
print(capture_reflection(
    investigation='<slug-describing-session-work>',
    went_well='<comma-separated positives>',
    could_improve='<comma-separated improvements>',
    domain='<domain-if-applicable>',
    proposed_learning='<key-takeaway-or-behavioral-change>'
))
"
```

## Step 3: Learning review

Call `learning_review()` to generate proposals for promoting pattern candidates.

```bash
PYTHONPATH=src .venv/bin/python3 -c "
from memory_mcp.tools.memory import learning_review
print(learning_review())
"
```

## Step 4: Present findings

Show the user:
1. What learnings were captured (new ones from step 1 + any previously captured this session)
2. The reflection summary
3. Any promotion proposals from the learning review

Wait for the user to approve/reject proposals before applying them.
