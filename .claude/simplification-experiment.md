# Simplification Experiment: Hook Consolidation

## Status: active
## Date: 2026-02-15
## Evaluation Date: 2026-03-15 (4 weeks)
## Branch: feature/musk-engineering-philosophy

## What Changed

Removed 3 hooks (14 → 11) based on hook-metrics.jsonl analysis of 460 invocations.

| Hook Removed | Lines | Data Evidence | Rationale |
|-------------|-------|---------------|-----------|
| auto-format.py | 81 | 71 invocations, 0 actual formatting runs | Dead — never formatted anything |
| checkpoint-validator.py | 101 | 14 invocations, 0 validations | Dead — never ran its logic. Section validation merged into checkpoint-reminder.py |
| post-edit-verify.py | 57 | 52 invocations, 52 advisories | Noisy — 52 "remember to test" reminders per session. completion-checklist enforces at session end |

Also simplified:
- spec-update-check.py: 251 → ~100 lines (simpler trigger matching)
- pre-flight-check.py: 190 → ~85 lines (focused on Python + Node only)

## Baseline Metrics (Before Changes)

Captured from 460 hook invocations in hook-metrics.jsonl:

| Metric | Value |
|--------|-------|
| completion-checklist block rate | 10/35 = 29% |
| session-handoff block rate | 1/10 = 10% |
| Total hook invocations | 460 |
| Skip rate | 235/460 = 51% |
| auto-format actions | 0/71 = 0% |
| checkpoint-validator actions | 0/14 = 0% |
| post-edit-verify advisories | 52/52 = 100% (all noise) |

## Reversal Criteria

| Trigger | What to Monitor | Action if Triggered |
|---------|----------------|---------------------|
| completion-checklist block rate > 50% | More sessions ending without tests run | Reinstate post-edit-verify.py |
| Formatting lint failures in PRs (>2 incidents) | CI catching formatting issues that pre-commit missed | Add `black --check` + `isort --check` to pre-commit-check.py |
| Checkpoint quality degradation | session-context.md files missing required sections | Verify checkpoint-reminder's merged validation is working; if not, reinstate standalone validator |
| Hook skip rate stays >50% | Remaining hooks still mostly skipping | Further consolidation needed |

## How to Evaluate

1. After the evaluation date, run this analysis against the current hook-metrics.jsonl:

```python
import json
from collections import Counter

metrics = []
with open('.claude/hook-metrics.jsonl') as f:
    for line in f:
        if line.strip():
            metrics.append(json.loads(line))

# Filter to post-change period (after 2026-02-15)
post = [m for m in metrics if m.get('ts', '') > '2026-02-15']

# Check completion-checklist block rate
cc = [m for m in post if m.get('name') == 'completion-checklist']
cc_blocks = sum(1 for m in cc if m.get('decision') == 'block')
cc_total = len(cc)
print(f"completion-checklist: {cc_blocks}/{cc_total} blocks = {cc_blocks/cc_total*100:.0f}%" if cc_total else "No data")

# Check skip rate
skips = sum(1 for m in post if m.get('decision') == 'skip')
print(f"Skip rate: {skips}/{len(post)} = {skips/len(post)*100:.0f}%" if post else "No data")
```

2. Compare against baseline values above.
3. If any reversal trigger is hit, follow the action column.
4. If no triggers hit and evaluation date passed, set status to `resolved`.
