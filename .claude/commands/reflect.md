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

## Step 2: 5 Whys root cause analysis

For each "could improve" item identified, trace the causal chain by asking "Why?" repeatedly until you reach a root cause or actionable insight:

1. **State the issue**: What went wrong or could be better?
2. **Why did this happen?** → first-level cause
3. **Why did that happen?** → deeper cause
4. **Continue** until you hit a root cause (typically 3-5 levels)

Write out each chain explicitly. Example:
- Spent too long on schema exploration → didn't check catalog first → assumed catalog wouldn't have join info → didn't read catalog docs → **Root cause: skipped pre-flight reference check**

## Step 3: Identify behavioral changes

From the root causes in Step 2, derive specific, actionable behavioral changes. Each change must be:
- **Concrete**: "Before writing a hook, check if PostToolUse provides tool_result" not "Be more careful with hooks"
- **Observable**: Someone could verify whether you did it
- **Scoped**: Applies to a specific situation, not a vague aspiration

Bad: "Be more thorough" / Good: "Run `grep` for existing usage before creating a new helper function"

## Step 4: Ask user probing questions

Use `AskUserQuestion` to ask the user 1-2 targeted questions about the improvements identified. Examples:
- "Do these root causes resonate? Is there a deeper issue I'm missing?"
- "Which of these behavioral changes would be most impactful for future sessions?"
- "I identified X as the root cause — does that match your experience, or was it something else?"

Wait for the user's response before proceeding. Incorporate their feedback into the reflection.

## Step 5: Capture session reflection

Call `capture_reflection()` with a structured summary including root causes and behavioral changes. This is MANDATORY even if individual learnings were already captured — reflections serve as session-level narrative for post-hoc review.

```bash
PYTHONPATH=src .venv/bin/python3 -c "
from memory_mcp.tools.memory import capture_reflection
print(capture_reflection(
    investigation='<slug-describing-session-work>',
    went_well='<comma-separated positives>',
    could_improve='<comma-separated improvements>',
    domain='<domain-if-applicable>',
    proposed_learning='<key-takeaway>',
    root_causes='<chain1>|<chain2>',
    behavioral_changes='<change1>|<change2>'
))
"
```

Format for `root_causes`: pipe-separated chains, each using `→` for causation. Example:
`"Slow schema exploration → didn't check catalog → skipped pre-flight check|Wrong join logic → assumed column names → didn't verify with DESCRIBE"`

Format for `behavioral_changes`: pipe-separated actionable changes. Example:
`"Always check catalog before schema exploration|Run DESCRIBE on target tables before writing joins"`

## Step 6: Learning review

Call `learning_review()` to generate proposals for promoting pattern candidates.

```bash
PYTHONPATH=src .venv/bin/python3 -c "
from memory_mcp.tools.memory import learning_review
print(learning_review())
"
```

## Step 7: Present findings and apply approved proposals

Show the user:
1. What learnings were captured (new ones from step 1 + any previously captured this session)
2. The reflection summary including root causes and behavioral changes
3. Any promotion proposals from the learning review

Wait for the user to approve/reject proposals. For each approved proposal, call `apply_proposal()`:

```bash
PYTHONPATH=src .venv/bin/python3 -c "
from memory_mcp.tools.memory import apply_proposal
print(apply_proposal(
    memory_id='<memory-id-from-proposal>',
    target_file='<relative-path-e.g.-.claude/commands/commit-push-pr.md>',
    action='append',  # 'append' or 'remove'
    content='<the-content-to-add-or-remove>',
    scope='personal'  # or 'universal'
))
"
```

**Note:** `target_file` must be in `.claude/commands/` or `.claude/agents/`. Use `action='append'` to add, `action='remove'` to remove.
