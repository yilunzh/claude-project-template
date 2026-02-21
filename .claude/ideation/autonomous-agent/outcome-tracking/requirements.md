# Requirements: Outcome Tracking (Gap 3)

## Status: DRAFT
## Last Updated: 2026-02-16
## Depends On: discovery.md
## Track: B (Musk 5-Step)

---

## 1. First-Principles Framing

**Why does this problem exist?**

Learning systems without outcome feedback optimize for repetition, not success. The Memory MCP captures what the agent learns (corrections, preferences, patterns) and how often those learnings are triggered (reinforcement count), but has no signal for whether those learnings led to good results.

**What's the fundamental need?**

The ability to answer: "Did this behavioral pattern actually work?" — measured by observable results (PR merged, user confirmed helpful) rather than proxies (loaded frequently).

**What's the simplest intervention?**

Add outcome data directly to memory YAML entries. The primary consumer (`learning_review()`) already reads all memory files — co-locating outcomes with memories eliminates the need for joins, separate storage, or new infrastructure.

---

## 2. Scope

### In Scope
- Memory YAML schema: optional `outcomes` list on each memory entry
- `track_outcome()` MCP tool for recording outcomes against specific memories
- `learning_review()` outcome-weighted scoring (complement model with reinforcement)
- Binary outcome types: merged, reverted, closed, positive_feedback, negative_feedback
- Simple ratio scoring: positive / total
- Lightweight post-merge reminder (advisory nudge to track outcomes)

### Out of Scope
- Metrics infrastructure refactor (agent-state.json / agent-summaries.jsonl) — separate initiative
- Trust scoring (Gap 5) — depends on this but is a separate build
- Session-inferred attribution — future upgrade if explicit coverage is too low
- Automated outcome detection (webhook, polling) — future upgrade
- Cross-project outcome aggregation — deferred per privacy decision
- Time-decayed scoring — deferred until data volume justifies complexity

---

## 3. User Stories

### Memory Management
- **US1**: As an agent, I can record an outcome for a specific memory so that the system tracks whether my behavior led to success or failure.
  - Acceptance: `track_outcome(memory_id="abc", result="merged", pr=42)` appends to memory's outcomes list
- **US2**: As a user, I can provide positive or negative feedback on a memory so that the system learns from my judgment.
  - Acceptance: `track_outcome(memory_id="abc", result="positive_feedback", context="helped fix the deploy")` works

### Learning Review
- **US3**: As `learning_review()`, I can weight proposals by outcome success rate so that I recommend patterns that actually work, not just patterns that fire often.
  - Acceptance: A memory with 1/5 success rate ranks lower than one with 4/5, even if the first has higher reinforcement count
- **US4**: As a user reviewing learning proposals, I can see outcome data alongside reinforcement data so that I understand why a proposal was ranked the way it was.
  - Acceptance: `learning_review()` output includes outcome stats (e.g., "3/4 outcomes positive") for memories that have outcomes

### Capture Support
- **US5**: As an agent, I get a reminder after PR-related activity to track outcomes so that I don't forget to record what happened.
  - Acceptance: Advisory nudge appears after PR merge/close suggesting `track_outcome()` for relevant memories

### Compatibility
- **US6**: As an existing user, my current memories continue to work without modification after outcome tracking is added.
  - Acceptance: Memories without `outcomes` field load and function normally; no migration required

---

## 4. Requirements Audit

| # | Requirement | Owner | First-Principles Rationale | Deletion Test (what breaks?) | Status |
|---|-------------|-------|---------------------------|------------------------------|--------|
| R1 | Memory YAML schema supports optional `outcomes` list | learning_review() | Outcomes must be stored somewhere. Co-location with memory data eliminates joins and separate storage. | No place to store outcomes → can't track anything | **Keep** |
| R2 | `track_outcome(memory_id, result, pr?, context?)` MCP tool | Agent / User | Need an interface to record outcomes. MCP tool matches existing memory system API surface. | No way to record outcomes → outcomes list stays empty forever | **Keep** |
| R3 | Result types: merged, reverted, closed, positive_feedback, negative_feedback | learning_review() | Need a vocabulary to classify outcomes. Binary types match the "binary + separate entries" decision. "closed" covers abandoned PRs. | No classification → can't compute positive/negative ratio | **Keep** |
| R4 | `learning_review()` ranks proposals by Laplace-smoothed outcome score | learning_review() | Primary consumer. Laplace smoothing: (positive+1)/(scoreable+2). Naturally handles small samples (1/1 → 0.67, not 1.0). This is the core value — distinguishing good patterns from bad. | learning_review() can't weight by outcomes → entire feature pointless | **Keep** |
| R5 | Reinforcement count as tiebreaker, not blended into score | learning_review() | Discovery decision D2 (complement). Outcome score is primary rank. Reinforcement breaks ties between memories with equal scores. Simpler than weighted blending, avoids the "popular but unproven beats proven-good" problem. | Equal-scoring memories appear in arbitrary order — minor | **Keep** |
| R6 | Neutral default: memories without outcomes score 0.5 | learning_review() | Laplace smoothing with 0 outcomes produces (0+1)/(0+2) = 0.5 automatically. No special-casing needed. Most memories will have no outcomes initially. | Memories without outcomes penalized or excluded → unfair ranking | **Keep** |
| R7 | Outcome stats displayed in `learning_review()` output | User | Transparency — if outcomes influence ranking, user should see why. Supports user judgment in approve/reject flow. | User can't understand why proposals are ranked as they are → trust issue | **Keep** |
| R8 | Backward compatible — no migration for existing memories | Existing users | Outcome field is optional (default empty list). Existing YAML files parse normally. Zero-cost adoption. | Existing memories break on upgrade → unacceptable | **Keep** |
| R9 | `get_outcome_summary(memory_id?)` MCP tool for querying outcome stats | User | Separate query interface for outcome data independent of learning review. | User must run full `learning_review()` just to see one memory's outcomes | **Delete** |
| R10 | Post-merge reminder: nudge to call `track_outcome()` after PR activity | Agent | Explicit-only attribution won't happen consistently without nudges. A lightweight reminder closes the gap between "explicit" and "forgotten." | Lower outcome capture rate → less data → weaker scoring | **Reinstated** |
| R11 | Time-decayed scoring: recent outcomes weighted more | learning_review() | Codebases evolve — a pattern that worked 6 months ago may not work now. Recent outcomes are more predictive. | Old outcomes have equal weight → stale patterns score well | **Delete** |
| R12 | Duplicate outcome prevention: warn if same PR already tracked | Agent | Prevents double-counting (e.g., agent calls `track_outcome()` twice for same PR). | Duplicate entries slightly skew success rates | **Delete** |
| R13 | Cross-project outcome aggregation | Harvester | Patterns promoted cross-project would carry outcome data. Stronger signal for harvester decisions. | Harvester promotes without outcome context → may promote bad patterns | **Delete** |
| R14 | Automated revert detection via git | Agent | Auto-detect reverted PRs and record negative outcomes without manual intervention. | Reverts only tracked if agent/user manually notices and records | **Delete** |

**Deletion target: 10%** — Current rate: 5 deleted / 14 total = **36%** (1 reinstated)

---

## 5. Deletion Log

| # | Deleted Item | Original Justification | Why Deleted | Reinstated? | Reinstatement Reason |
|---|-------------|------------------------|-------------|-------------|---------------------|
| D1 | R9: `get_outcome_summary()` tool | Separate query interface for outcome data | Redundant — `learning_review()` already reads all memories and displays outcome stats (R7). Users can also read YAML directly. No unique consumer. | No | — |
| D2 | R10: Post-merge reminder hook | Improve outcome capture rate | Originally deleted: adds hook complexity, contradicts explicit-only attribution. | **Yes** | Explicit-only won't happen consistently without nudges. Reinstated as lightweight advisory reminder, not automated detection. Still explicit — user decides whether to act on the nudge. |
| D3 | R11: Time-decayed scoring | Recent outcomes more predictive than old | Premature optimization. With <20 outcomes per memory, decay constants are meaningless. Simple ratio serves the same purpose at current scale. Add when a memory accumulates enough outcomes that decay matters. | No | — |
| D4 | R12: Duplicate prevention | Prevent double-counting | Negligible impact. If a PR is tracked twice, a memory's success rate shifts by ~5% at most (assuming ~10 outcomes). Not worth the validation code. | No | — |
| D5 | R13: Cross-project aggregation | Stronger harvester signal | No current consumer. Privacy decision was "project-specific now." Building aggregation before cross-project sharing exists is premature. | No | — |
| D6 | R14: Automated revert detection | Reduce manual effort | Contradicts explicit-only attribution decision. Auto-detection requires git parsing logic, heuristics for distinguishing reverts from cherry-picks, and a trigger mechanism. All of that complexity for a signal the user can provide manually. | No | — |

---

## 6. Simplified Design (Post-Deletion)

### What remains: 9 requirements, 6 user stories, ~4-6 files changed

**Memory YAML change:**
```yaml
# Existing fields unchanged
id: abc-123
type: correction
content: "Always use .venv/bin/python3"
reinforcement_count: 5
# New field — optional, defaults to empty list
outcomes:
  - result: merged
    pr: 42
    ts: "2026-02-16T12:00:00Z"
    context: "Used correct Python path in deploy script"
  - result: positive_feedback
    ts: "2026-02-17T09:00:00Z"
    context: "User confirmed this saved debugging time"
```

**`track_outcome()` MCP tool:**
```
track_outcome(
  memory_id: str,      # Required — which memory
  result: str,         # Required — merged|reverted|closed|positive_feedback|negative_feedback
  pr: int?,            # Optional — PR number for PR-related outcomes
  context: str?        # Optional — free-text description
)
```

**`learning_review()` scoring change:**
```
For each memory:
  adjusted_score = (positive + 1) / (scoreable + 2)   # Laplace smoothing

  # Ranking: sort by adjusted_score DESC, tiebreak by times_reinforced DESC
  # 0 outcomes → 0.5 (neutral), 1/1 → 0.67 (not overconfident), 10/10 → 0.92 (strong)
```

---

## 7. Acceleration Opportunities

- **No migration**: `outcomes` field is optional. Existing memories work unchanged. Zero deployment friction.
- **Single-file schema change**: Memory YAML loader just needs to handle the new field. No database, no migration script.
- **Existing MCP patterns**: `track_outcome()` follows exact same patterns as `capture_memory()` — read YAML, modify, write back. Reuse existing file I/O.
- **learning_review() is the only consumer to modify**: One function change, not a system-wide refactor.
- **Piggyback reminder on existing hooks**: The post-merge reminder can be added to an existing hook (e.g., `completion-checklist.py` or `memory-check.py`) rather than creating a new hook file. Advisory only — no blocking.

---

## 8. Automation Assessment

| Candidate | Automate? | Justification |
|-----------|-----------|---------------|
| Outcome recording | No — explicit with advisory nudge | Discovery decision D3. Explicit attribution, but with a reminder to avoid forgotten outcomes. Still manual — agent decides whether to act. |
| Success rate computation | Yes — in learning_review() | Simple arithmetic, no judgment needed. Must be computed to be useful. |
| Outcome display in proposals | Yes — in learning_review() | Transparency requirement. Computed and displayed automatically. |
| Revert detection | No — deleted (R14) | Contradicts explicit-only. Manual for now. |
| Outcome-based promotion | No — future | No cross-project consumer yet. |

**Only automate what survived Steps 1-4**: Success rate computation and outcome display — both are trivial, internal to `learning_review()`, and serve the core value.

---

## 9. Risks + Fastest Validating Experiments

| Risk | Likelihood | Impact | Fastest Validation |
|------|-----------|--------|-------------------|
| Explicit attribution coverage too low (<10% of outcomes tracked) | Medium | Medium — scoring falls back to reinforcement (safe) | Use for 2-3 PRs, count how many outcomes get explicitly attributed. If <1 per PR, consider adding reminder hook (reinstating R10). |
| YAML files grow large with many outcomes | Low | Low — each outcome is ~100 bytes, 50 outcomes = 5KB | Monitor file sizes after 20+ outcomes. Cap list if needed (oldest dropped). |
| Success rate misleading with sparse data | Medium | Low — 0.5 neutral default handles no-data case | Test with 1-3 outcomes: does the scoring produce sensible rankings? |
| `learning_review()` scoring formula wrong | Medium | Medium — bad recommendations | A/B test: run learning_review() with and without outcome weighting on same memory set, compare output quality. |
| Complement model weighting awkward | Low | Medium — either outcome or reinforcement dominates | Tune `outcome_weight = min(count/10, 1.0)` threshold. Start with 10, adjust based on typical outcome volume. |

**Cheapest experiment**: Track outcomes for the next 3 PRs manually. Run `learning_review()` with the prototype weighting. Does the output improve? If yes, build it. If no, reconsider.

---

## 10. Success Criteria

1. `track_outcome()` MCP tool successfully records outcomes to memory YAML files
2. `learning_review()` output visibly changes based on outcome data (memories with good outcomes rank higher)
3. Existing memories without outcomes continue to work unchanged
4. A memory with 0/3 success rate ranks lower than one with 3/3, even if the first has higher reinforcement count
5. User can see outcome stats in `learning_review()` output

---

## 11. Constraints

- **No new infrastructure files** — outcomes stored in existing memory YAML files
- **No new hooks** — outcome recording is explicit/manual
- **Backward compatible** — existing memories unaffected
- **Project-specific** — no cross-project outcome sharing (deferred)
- **≤6 files changed** — schema, tool, learning_review, reminder hook, tests
