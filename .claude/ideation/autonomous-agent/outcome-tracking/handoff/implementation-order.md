# Implementation Order: Outcome Tracking

## Suggested Build Sequence

### Session 1: Foundation + Core Tool

1. **Story 1.1**: Add constants (`VALID_OUTCOME_RESULTS`, `POSITIVE_OUTCOMES`, etc.) and validation to `memory.py`
2. **Story 1.2**: Implement `track_outcome()` MCP tool
3. **Story 3.1**: Add outcome reminder to `memory-check.py` (independent, can do in parallel or at end)
4. Manual test: call `track_outcome()` against a real memory, verify YAML output

### Session 2: Scoring + Integration

5. **Story 2.1**: Add `_compute_outcome_score()` with Laplace smoothing
6. **Story 2.2**: Modify `learning_review()` — sort by adjusted_score, add outcome display
7. Manual test: run `learning_review()` with memories that have outcomes, verify ranking and display

### Session 3: Tests + Polish

8. **Story 4.1**: Unit tests for validation, track_outcome, scoring
9. **Story 4.2**: Integration tests for learning_review with outcomes
10. Run full test suite, lint check, verify clean

## Parallelization Opportunities

- Stories 1.2 and 2.1 can be built in parallel (both depend only on 1.1)
- Story 3.1 is fully independent — can be done any time
- Stories 4.1 and 4.2 can be written in parallel

## Critical Path

```
1.1 → 1.2 → (manual test) → 2.1 → 2.2 → (manual test) → 4.1 + 4.2 → done
```

Story 3.1 slots in anywhere.
