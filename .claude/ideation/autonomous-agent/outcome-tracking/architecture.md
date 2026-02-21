# Architecture: Outcome Tracking (Gap 3)

## Status: DRAFT
## Last Updated: 2026-02-21
## Depends On: design-specs/outcome-tracking.md
## Track: B (Musk 5-Step)

---

## Architecture Overview

This is a **modification-only** build. No new modules, no new infrastructure, no new architectural layers. All changes live within the existing Memory MCP module and hook system.

```
┌─────────────────────────────────────────────┐
│  Memory MCP (src/memory_mcp/tools/memory.py)│
│                                             │
│  Existing:                                  │
│    capture_memory()                         │
│    reinforce_memory()                       │
│    learning_review()  ← MODIFY (scoring)    │
│    validate_memory_entry() ← MODIFY (schema)│
│                                             │
│  New:                                       │
│    track_outcome()    ← ADD (1 function)    │
│    _compute_outcome_score()  ← ADD (helper) │
└─────────────────────────────────────────────┘
             │
             │  reads/writes
             ▼
┌─────────────────────────────────────────────┐
│  .claude/memory/{type}/*.yaml               │
│  (existing files, new 'outcomes' field)     │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  .claude/hooks/memory-check.py              │
│  (existing Stop hook — ADD reminder logic)  │
└─────────────────────────────────────────────┘
```

**Layers: 1** (Memory MCP tool module). No middleware, no API server, no database, no message queue.

---

## 5-Step Deletion Pass

For every component in the design spec: "What breaks if this doesn't exist?"

| Component | What breaks without it? | Verdict |
|-----------|------------------------|---------|
| `outcomes` field on YAML | Can't store outcomes → entire feature impossible | **Keep** — fundamental |
| `track_outcome()` tool | No interface to record → users edit YAML manually (error-prone) | **Keep** — essential UX |
| `_compute_outcome_score()` | learning_review() can't score by outcomes | **Keep** — core value |
| `_compute_combined_score()` | Can inline into learning_review() directly? Yes, but same function in both proposal ranking and rollback display → 2 call sites. Justifies extraction. | **Keep** — serves 2 use cases |
| Validation in `validate_memory_entry()` | Bad data silently accepted → corrupt outcomes | **Keep** — data integrity |
| learning_review() display changes | User can't see WHY proposals are ranked differently | **Keep** — transparency (R7) |
| memory-check.py reminder | Lower capture rate, but system still works | **Keep** — reinstated by user decision |
| VALID_OUTCOME_RESULTS constant | Hardcode strings inline? Would work but error-prone. 3 consumers (validate, track_outcome, score). | **Keep** — 3 use sites |
| POSITIVE_OUTCOMES / NEGATIVE_OUTCOMES / NEUTRAL_OUTCOMES sets | Could compute from VALID_OUTCOME_RESULTS, but explicit sets are clearer and O(1) lookup | **Keep** — clarity |

**Deletion result: 0 components deleted.** Everything in the design spec is already minimal. The real deletion happened at the requirements level (36% deletion rate). Architecture has nothing left to cut.

---

## 5-Step Simplification Pass

### Layer Count: 1

| Layer | What it does | Justification |
|-------|-------------|---------------|
| Memory MCP tools | Stores, retrieves, and scores memory entries with outcomes | Single module handles all outcome logic. No separation needed at this scale. |

**Target: ≤3 layers. Actual: 1 layer.** Pass.

### Abstraction Check

| Abstraction | Use cases NOW | Justified? |
|-------------|--------------|-----------|
| `_compute_outcome_score()` | learning_review() proposals + rollback candidates | Yes — 2 call sites |
| VALID_OUTCOME_RESULTS set | validate_memory_entry(), track_outcome(), _compute_outcome_score() | Yes — 3 call sites |
| POSITIVE_OUTCOMES / NEGATIVE_OUTCOMES sets | _compute_outcome_score() | 1 call site — borderline. But serves clarity: explicit classification of which results are positive vs negative. Keep for readability. |

### "Utils" / "Helpers" Check

No utils module. No helpers module. All functions live in the existing `memory.py` where they're consumed. Pass.

---

## Metrics Infrastructure Decision

**The metrics-infrastructure.md 17-file refactor is NOT part of this build.**

| Concern | This build | Metrics infra (deferred) |
|---------|-----------|-------------------------|
| Storage | Memory YAML files (existing) | New agent-state.json + agent-summaries.jsonl |
| Scope | Outcome data only | Hook metrics + outcomes + trust |
| Files touched | ~4 | ~17 |
| New concepts | 1 (outcomes field) | 3 (tiered storage, session flush, namespaced state) |

The metrics infrastructure solves hook metrics performance (O(n) → O(1), skip waste, file growth). Those are legitimate problems but orthogonal to outcome tracking. If/when the metrics refactor happens, outcome data stays in memory YAML files — it doesn't move to agent-state.json because the primary consumer (learning_review) reads YAML files anyway.

**Outcome tracking and metrics infrastructure are permanently decoupled.** Not "build later" — they serve different consumers via different storage.

---

## Schedule Check

| Metric | Value | Gate |
|--------|-------|------|
| Files modified | 4 | — |
| New files | 0 | — |
| Estimated new code | ~120-150 lines | — |
| Estimated modified code | ~40-60 lines | — |
| Test additions | ~80-100 lines | — |
| **Estimated effort** | **<1 sprint** | ≤2 sprints ✓ |

**This is a 2-3 day build** for a focused agent. Single PR, no phased rollout needed.

---

## Data Model

### Outcome Entry (within memory YAML)

```yaml
outcomes:
  - result: merged                    # Required: enum
    ts: '2026-02-21'                  # Required: ISO date
    pr: 42                            # Optional: integer
    context: "Deployed successfully"  # Optional: string
```

### Constants

```python
VALID_OUTCOME_RESULTS = {"merged", "reverted", "closed", "positive_feedback", "negative_feedback"}
POSITIVE_OUTCOMES = {"merged", "positive_feedback"}
NEGATIVE_OUTCOMES = {"reverted", "negative_feedback"}
NEUTRAL_OUTCOMES = {"closed"}
```

### Scoring Formula (Laplace Smoothing)

```
adjusted_score = (positive + 1) / (scoreable + 2)

Ranking: sort by adjusted_score DESC, tiebreak by times_reinforced DESC
```

Properties:
- 0 outcomes → 0.5 (neutral)
- 1/1 → 0.67 (slightly positive, not overconfident)
- 10/10 → 0.92 (strong, still not 1.0)
- Naturally handles small samples without tuning parameters

---

## API Contract

### `track_outcome(memory_id, result, pr?, context?) → str`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| memory_id | string | Yes | Memory ID to attach outcome to |
| result | string (enum) | Yes | merged, reverted, closed, positive_feedback, negative_feedback |
| pr | integer | No | PR number |
| context | string | No | Free-text description |

**Returns:** Confirmation string with outcome summary, or error string.

**Side effects:** Appends to memory YAML file's `outcomes` list. Atomic write.

---

## Security Cross-Reference (docs/PATTERNS.md)

| Check | Applicable? | Status |
|-------|------------|--------|
| Input validation | Yes — result enum, memory_id lookup | Handled in tool validation |
| Path traversal | Yes — memory_id could be crafted | Existing `_find_memory_by_id()` resolves within `.claude/memory/` only |
| YAML injection | Low risk — we write structured data via `_atomic_write_yaml()` | Safe — PyYAML safe_dump |
| Secrets in outcomes | Possible — context field is free-text | Advisory: don't put secrets in context. No enforcement needed for local-only data. |
| CSRF / XSS / Headers | N/A — no web interface | — |

**No security concerns.** All operations are local file I/O within the user's own `.claude/memory/` directory, using existing safe write patterns.

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| YAML file size growth | Low | Low | Each outcome ~100 bytes. 50 outcomes = 5KB. Monitor; add cap if needed. |
| Laplace smoothing too conservative/aggressive | Low | Low | Smoothing has one "parameter" (the +1/+2 pseudocounts). Could adjust to +2/+4 for heavier smoothing. Easy to change. |
| Low capture rate (explicit-only) | Medium | Low | Safe fallback to reinforcement. Reminder hook helps. Monitor after 2-3 weeks. |
| learning_review() output too verbose | Low | Low | Only show outcome stats for memories that have outcomes. No-data memories get one-line note. |
| Race condition on YAML write | Very low | Low | `_atomic_write_yaml()` uses temp-file-then-rename. Same pattern as all other memory writes. |

---

## Implementation Phases

**Single phase — no phased rollout needed.**

| Order | What | Why first |
|-------|------|-----------|
| 1 | Schema constants + validation | Foundation — everything depends on this |
| 2 | `track_outcome()` tool | Can manually test with real memories |
| 3 | `_compute_outcome_score()` + `_compute_combined_score()` | Scoring logic, testable in isolation |
| 4 | `learning_review()` modifications | Integrate scoring into output |
| 5 | `memory-check.py` reminder | Advisory nudge — lowest priority |
| 6 | Tests for all of the above | Throughout, but comprehensive pass at end |

**All in one PR. One review. Ship it.**
