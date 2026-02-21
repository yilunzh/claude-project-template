# Design Specification: Outcome Tracking

## Status: DRAFT
## Last Updated: 2026-02-17
## Depends On: requirements.md
## Track: B (Musk 5-Step)

---

## Component Inventory

4 components to specify. Elimination check applied to each.

| # | Component | Eliminate? | Merge? | Verdict |
|---|-----------|-----------|--------|---------|
| C1 | Memory YAML schema change | No — nowhere else to store outcomes | No — unique concern | **Specify** |
| C2 | `track_outcome()` MCP tool | No — need an interface to record | Could merge with `reinforce_memory()`? No — different semantics (reinforcement ≠ outcome) | **Specify** |
| C3 | `learning_review()` scoring + display | No — primary consumer, the whole point | Already part of existing function — modify, don't create new | **Specify** (modification) |
| C4 | Post-merge reminder | No — reinstated requirement R10 | Merge into existing `memory-check.py` (Stop hook, advisory) — same trigger point, same pattern | **Specify** (merged into existing hook) |

**Result:** 4 components, 0 eliminated, 1 merged into existing file. Net new files: 0 (all modifications to existing code).

---

## C1: Memory YAML Schema Change

### Current Schema (relevant fields)

```yaml
id: correction-always-use-venv-bin-python3
type: correction
summary: "Always use .venv/bin/python3"
detail: "System Python is 3.9.6, venv is 3.13..."
times_reinforced: 5
first_seen: '2026-02-15'
last_seen: '2026-02-16'
status: active
# ... other fields: signal, domain, tables, phase, scope, source_sessions, etc.
```

### Addition

```yaml
# New field — optional, defaults to absent (treated as empty list)
outcomes:
  - result: merged        # Required: merged|reverted|closed|positive_feedback|negative_feedback
    pr: 42                # Optional: PR number (for PR-related outcomes)
    ts: '2026-02-16'      # Required: ISO date when outcome was recorded
    context: "Used correct Python path in deploy script"  # Optional: free-text
```

### Schema Rules

- **Field name:** `outcomes`
- **Type:** List of dicts. Each dict is one outcome entry.
- **Default:** Absent from file (not an empty list). Treated as `[]` when read.
- **Outcome entry required fields:** `result`, `ts`
- **Outcome entry optional fields:** `pr`, `context`
- **Valid result values:** `merged`, `reverted`, `closed`, `positive_feedback`, `negative_feedback`
- **Positive results:** `merged`, `positive_feedback`
- **Negative results:** `reverted`, `negative_feedback`
- **Neutral results:** `closed` (ambiguous — doesn't count as positive or negative in scoring)

### Validation

Add to `validate_memory_entry()`:

```python
VALID_OUTCOME_RESULTS = {"merged", "reverted", "closed", "positive_feedback", "negative_feedback"}
POSITIVE_OUTCOMES = {"merged", "positive_feedback"}
NEGATIVE_OUTCOMES = {"reverted", "negative_feedback"}
NEUTRAL_OUTCOMES = {"closed"}

# In validate_memory_entry():
if "outcomes" in entry:
    if not isinstance(entry["outcomes"], list):
        return "outcomes must be a list"
    for i, outcome in enumerate(entry["outcomes"]):
        if "result" not in outcome:
            return f"outcome[{i}] missing required field 'result'"
        if outcome["result"] not in VALID_OUTCOME_RESULTS:
            return f"outcome[{i}] invalid result: {outcome['result']}"
        if "ts" not in outcome:
            return f"outcome[{i}] missing required field 'ts'"
```

### Backward Compatibility

- Existing memories without `outcomes` field continue to load normally.
- `validate_memory_entry()` only checks `outcomes` if the field is present.
- No migration script needed. Memories organically gain outcomes as users track them.

---

## C2: `track_outcome()` MCP Tool

### Elimination Check

Can we skip the tool and have users edit YAML directly? No — manual YAML editing is error-prone (invalid result types, missing ts, wrong format). A tool provides validation, consistent formatting, and discoverability.

### Tool Registration

```python
@register_tool(
    name="track_outcome",
    description=(
        "Record an outcome (PR merged/reverted, user feedback) for a specific memory. "
        "Links real-world results to behavioral learnings so learning_review() can "
        "weight proposals by success rate."
    ),
    parameters={
        "memory_id": {
            "type": "string",
            "description": "ID of the memory to track an outcome for (e.g., 'correction-always-use-venv')"
        },
        "result": {
            "type": "string",
            "description": "Outcome type: merged, reverted, closed, positive_feedback, negative_feedback",
            "enum": ["merged", "reverted", "closed", "positive_feedback", "negative_feedback"]
        },
        "pr": {
            "type": "integer",
            "description": "PR number (optional, for PR-related outcomes)"
        },
        "context": {
            "type": "string",
            "description": "Free-text description of what happened (optional)"
        },
    },
    required=["memory_id", "result"],
)
```

### Function Behavior

```python
def track_outcome(memory_id: str, result: str, pr: int = None, context: str = "") -> str:
    """
    1. Validate result against VALID_OUTCOME_RESULTS
    2. Find memory file by ID (reuse _find_memory_by_id() pattern from reinforce_memory)
    3. Read YAML
    4. Append outcome entry to outcomes list:
       {
         "result": result,
         "ts": date.today().isoformat(),
         "pr": pr,           # only if provided
         "context": context,  # only if provided
       }
    5. Atomic write back
    6. Return confirmation string with outcome summary
    """
```

### Return Values

- **Success:** `"Tracked outcome for '{memory_id}': {result} (PR #{pr}). Total outcomes: {n} ({positive} positive, {negative} negative)."`
- **Memory not found:** `"Error: Memory '{memory_id}' not found."`
- **Invalid result:** `"Error: Invalid result '{result}'. Must be one of: merged, reverted, closed, positive_feedback, negative_feedback."`

### Edge Cases

- Memory with status `decayed` or `superseded`: Allow outcome tracking anyway. Outcomes are historical facts; memory status is a lifecycle concern. A decayed memory that had good outcomes might be worth reconsidering.
- Multiple outcomes for same PR: Allowed (no duplicate prevention per deletion D4). Agent responsibility.

---

## C3: `learning_review()` Scoring + Display Modification

### Elimination Check

Can we skip modifying `learning_review()`? No — it's the primary consumer and the whole point of tracking outcomes.

### Current Behavior (what changes)

Currently `learning_review()` buckets memories and generates proposals for `pattern_candidate` entries. Ranking is implicit — candidates are listed in file-scan order, with `times_reinforced` shown but not used for sorting.

### Scoring Addition

Add outcome-aware scoring to proposal ranking using **Laplace smoothing**:

```python
def _compute_outcome_score(memory: dict) -> tuple[float, int, int]:
    """
    Returns (adjusted_score, positive_count, scoreable_count).

    Uses Laplace smoothing: (positive + 1) / (scoreable + 2).
    - No outcomes → 0.5 (neutral)
    - 1/1 positive → 0.67 (slightly positive, not proven)
    - 10/10 positive → 0.92 (very strong, still not 1.0)
    - Small samples pulled toward 0.5; converges to true ratio with data.
    """
    outcomes = memory.get("outcomes", [])
    scoreable = [o for o in outcomes if o["result"] in POSITIVE_OUTCOMES | NEGATIVE_OUTCOMES]
    positive = sum(1 for o in scoreable if o["result"] in POSITIVE_OUTCOMES)
    adjusted_score = (positive + 1) / (len(scoreable) + 2)
    return (adjusted_score, positive, len(scoreable))
```

**No combined score needed.** Ranking is:
1. Sort by `adjusted_score` descending (quality, sample-size-aware)
2. Tiebreak by `times_reinforced` descending (frequency as secondary signal)

This replaces the previous blending formula. Reinforcement is no longer mixed into the score — it's a tiebreaker. The Laplace smoothing naturally handles the "no data" case (0.5) and the "small sample" case (1/1 → 0.67, not 1.0).

### Display Addition

Add outcome stats to each proposal block in the markdown output:

```markdown
### Proposal 1: Promote to project convention

**Memory:** correction-always-use-venv-bin-python3
**Reinforced:** 5 times
**Outcomes:** 3/4 positive (merged: 3, reverted: 1) ← NEW
**Combined score:** 0.72 ← NEW

**Summary:** Always use .venv/bin/python3 — system Python is 3.9.6
...
```

For memories without outcomes:
```markdown
**Outcomes:** No outcome data (score neutral)
```

### Proposal Ranking

Sort proposals by `adjusted_score` descending, tiebreak by `times_reinforced` descending. Currently unranked — this adds meaningful ordering.

### Rollback Candidate Enhancement

Rollback candidates (memories contradicting promoted ones) should also show outcome data. A rollback candidate with positive outcomes is more concerning than one with no data.

---

## C4: Post-Merge Reminder (Merged into `memory-check.py`)

### Elimination Check

Can this be eliminated? User reinstated it (R10). Explicit-only won't happen without nudges.

### Merge Decision

Merge into `memory-check.py` rather than creating a new hook. Rationale:
- `memory-check.py` is a Stop hook (advisory) — fires at session end
- It already reminds about learning capture (`/reflect`)
- Adding "track outcomes for any PRs this session" fits naturally
- Same trigger point, same advisory pattern, same file

### Behavior

Add to `memory-check.py` main flow:

```python
def _check_outcome_tracking():
    """
    Check if PRs were merged/closed this session but no outcomes were tracked.

    1. Search transcript for PR merge/close signals:
       - "merged" + PR number pattern
       - "gh pr merge" invocations
       - "pull request" + "merged" / "closed"
    2. Search transcript for track_outcome() calls
    3. If PR signals found but no track_outcome calls → suggest tracking
    """
    # ... regex on transcript text (same pattern as completion-checklist.py)
```

### Advisory Message

```
Outcome tracking reminder: This session appears to have PR activity
but no outcomes were tracked. Consider calling track_outcome() for
memories that influenced the work. Example:
  track_outcome(memory_id="<id>", result="merged", pr=<number>)
```

### Detection Heuristics

Keep simple — false positives are fine for an advisory:

```python
PR_ACTIVITY_PATTERNS = [
    r"gh\s+pr\s+merge",
    r"pull\s+request\s+#?\d+.*merged",
    r"pr\s+#?\d+.*merged",
    r"merged\s+pr\s+#?\d+",
]

OUTCOME_TRACKED_PATTERNS = [
    r"track_outcome",
]
```

If any `PR_ACTIVITY_PATTERNS` match AND no `OUTCOME_TRACKED_PATTERNS` match → show reminder.

---

## Integration Flow

### End-to-End Sequence

```
1. Agent works on a task, memories are loaded via load_relevant_memories()
2. Agent produces code, creates PR, PR gets merged
3. Session ends → memory-check.py fires (Stop hook)
4. Reminder: "PR activity detected, no outcomes tracked"
5. Agent (next session or same) calls:
   track_outcome(memory_id="correction-xyz", result="merged", pr=42, context="...")
6. Outcome appended to memory YAML file
7. Later: learning_review() runs
8. Proposals sorted by combined score (reinforcement + outcomes)
9. User sees: "3/4 positive outcomes" next to each proposal
10. User makes better-informed accept/reject decisions
```

### Data Flow Diagram

```
track_outcome()  ──writes──►  .claude/memory/{type}/{file}.yaml
                                      │
                                      │ (outcomes list)
                                      ▼
learning_review() ──reads──►  all memory YAML files
                                      │
                                      │ (_compute_outcome_score + _compute_combined_score)
                                      ▼
                              Ranked proposals with outcome stats
                                      │
                                      ▼
                              User reviews and decides
```

### No New Files Created

| Change | File | Type |
|--------|------|------|
| Schema validation | `src/memory_mcp/tools/memory.py` | Modify |
| `track_outcome()` tool | `src/memory_mcp/tools/memory.py` | Add function |
| Scoring functions | `src/memory_mcp/tools/memory.py` | Add functions |
| `learning_review()` display | `src/memory_mcp/tools/memory.py` | Modify function |
| Post-merge reminder | `.claude/hooks/memory-check.py` | Modify |
| Tests | `tests/test_memory_tools.py` (or similar) | Modify |

**Total: ~4 files modified, 0 new files created.**

---

## Open Design Questions

None — all decisions made in discovery and requirements phases.
