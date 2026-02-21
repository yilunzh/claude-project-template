# Handoff: Outcome Tracking (Gap 3)

## Executive Summary

Outcome tracking adds the ability to record real-world results (PR merged/reverted, user feedback) against Memory MCP entries. This closes the feedback loop: the system can now distinguish patterns that lead to successful outcomes from patterns that are merely frequently triggered.

**Build scope:** ~150 lines new code, ~50 lines modified, 4 files changed, 0 new files. Single PR, <1 sprint.

**Key design decisions:**
- Outcomes stored directly in memory YAML files (not in separate infrastructure)
- Laplace-smoothed scoring: `(positive+1)/(scoreable+2)` — handles small samples gracefully
- Explicit attribution only — agent/user names specific memories. No session inference.
- Binary outcome types: merged, reverted, closed, positive_feedback, negative_feedback
- Metrics infrastructure refactor (17-file) permanently decoupled — different problem, different storage

## What Gets Built

| Component | File | Change Type |
|-----------|------|-------------|
| Outcome constants + validation | `src/memory_mcp/tools/memory.py` | Add constants, modify `validate_memory_entry()` |
| `track_outcome()` MCP tool | `src/memory_mcp/tools/memory.py` | Add function + `@register_tool` |
| `_compute_outcome_score()` | `src/memory_mcp/tools/memory.py` | Add function |
| `learning_review()` ranking + display | `src/memory_mcp/tools/memory.py` | Modify function |
| Post-merge outcome reminder | `.claude/hooks/memory-check.py` | Add `_check_outcome_tracking()` |
| Tests | `tests/test_memory.py` + `tests/test_memory_check.py` | Extend existing test classes + add new |

## Key Technical Details

### Memory YAML Addition
```yaml
outcomes:
  - result: merged
    ts: '2026-02-21'
    pr: 42
    context: "Deployed successfully"
```

### Scoring
```
adjusted_score = (positive + 1) / (scoreable + 2)
Rank by adjusted_score DESC, tiebreak by times_reinforced DESC
```

### Tool Interface
```
track_outcome(memory_id: str, result: str, pr?: int, context?: str) → str
```

## What Needs Human Refinement (~15-20%)

1. **Reminder hook regex tuning** — PR activity detection patterns may need adjustment based on actual transcript patterns. Start with proposed patterns, tune after 1-2 sessions.
2. **Scoring display format** — The exact wording of outcome stats in `learning_review()` output ("3/4 positive, score: 0.71") may need polish for readability.
3. **learning_review() sort integration** — The existing function builds markdown in sections. Sorting pattern_candidates by score requires restructuring how the candidates list is processed. May need minor refactoring of the function internals.

## Testing Strategy

**~27 test cases** across 5 areas. All follow existing patterns — no new test infrastructure.

| Area | File | Class | Cases | Type |
|------|------|-------|-------|------|
| Schema validation | `tests/test_memory.py` | `TestSchemaValidation` (extend) | 5 | Unit |
| `track_outcome()` tool | `tests/test_memory.py` | `TestTrackOutcome` (new) | 8 | Unit |
| `_compute_outcome_score()` | `tests/test_memory.py` | `TestOutcomeScoring` (new) | 9 | Unit |
| `learning_review()` outcomes | `tests/test_memory.py` | `TestLearningReview` (extend) | 5 | Integration |
| Reminder hook | `tests/test_memory_check.py` | `TestMain` (extend) | 4 | Unit (mocked) |

**Key testing patterns (from existing codebase):**
- `tmp_memory` fixture provides monkeypatched temp memory directory
- `_create_memory()` helper writes YAML directly with configurable overrides (including `outcomes` field)
- Tool return strings checked for success/error markers
- YAML files read back and verified for correct content
- Hook tests use `patch.object()` and `patch.dict(os.environ, {"CLAUDE_TRANSCRIPT": ...})`
- Scoring tests use `pytest.approx()` for float comparisons

**Critical test properties to verify:**
- Laplace smoothing: 1/1 positive scores 0.67, not 1.0 (small sample pulled toward 0.5)
- Ranking: 4/5 positive beats 1/5 positive regardless of reinforcement count
- `closed` outcomes excluded from scoring (neutral — neither positive nor negative)
- Backward compatibility: memories without `outcomes` field load, validate, and score at 0.5

## Verification Criteria

- [ ] `track_outcome()` records outcomes to YAML files correctly
- [ ] Existing memories without outcomes load and validate without errors
- [ ] `learning_review()` ranks candidates by adjusted_score
- [ ] `learning_review()` displays outcome stats per proposal
- [ ] Memory with 0/3 success rate ranks below one with 3/3
- [ ] Memory with 1/1 success rate ranks below one with 10/10 (Laplace smoothing working)
- [ ] Post-merge reminder fires when PR activity detected but no track_outcome called
- [ ] All ~27 new test cases pass
- [ ] All existing tests still pass
- [ ] `ruff check .` clean
