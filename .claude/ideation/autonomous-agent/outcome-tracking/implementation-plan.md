# Implementation Plan: Outcome Tracking (Gap 3)

## Status: DRAFT
## Last Updated: 2026-02-21
## Depends On: architecture.md
## Track: B (Musk 5-Step)

---

## Scope Gate Check

- Total stories: **7**
  - [x] ≤15 stories
- Estimated duration: **<1 sprint (2-3 days)**
  - [x] ≤2 sprints

---

## Epic Overview

| Epic | Description | Stories | Complexity |
|------|-------------|---------|------------|
| E1: Schema + Tool | Outcome constants, validation, `track_outcome()` tool | 2 stories | S |
| E2: Learning Review | Scoring function, `learning_review()` modifications | 2 stories | M |
| E3: Capture Support | Post-merge reminder in `memory-check.py` | 1 story | S |
| E4: Testing | Unit + integration tests | 2 stories | S |

---

## Epic 1: Schema + Tool

**Goal:** Enable recording outcomes against memory entries.
**Dependencies:** None — foundational.

### Story 1.1: Add outcome schema constants and validation

**As a** memory system maintainer
**I want** outcome-related constants and validation in `memory.py`
**So that** outcome data is validated consistently

**Acceptance Criteria:**
- [ ] `VALID_OUTCOME_RESULTS`, `POSITIVE_OUTCOMES`, `NEGATIVE_OUTCOMES`, `NEUTRAL_OUTCOMES` constants defined
- [ ] `validate_memory_entry()` validates `outcomes` field when present (list of dicts, required `result` + `ts`, valid result enum)
- [ ] Memories without `outcomes` field pass validation unchanged

**Technical Notes:**
- Add constants near existing `VALID_MEMORY_TYPES`, `VALID_SCOPES`, etc.
- Validation is additive — only checks `outcomes` if the key exists in the dict

**Test Requirements:**
- [ ] Unit: validate_memory_entry() accepts memory with valid outcomes
- [ ] Unit: validate_memory_entry() rejects invalid result types
- [ ] Unit: validate_memory_entry() accepts memory without outcomes field

**Complexity:** S
**Depends On:** None

---

### Story 1.2: Implement `track_outcome()` MCP tool

**As an** agent
**I want** to call `track_outcome(memory_id, result, pr?, context?)`
**So that** I can record whether a memory led to a positive or negative real-world result

**Acceptance Criteria:**
- [ ] Tool registered via `@register_tool` with correct parameters and `required=["memory_id", "result"]`
- [ ] Appends outcome entry `{result, ts, pr?, context?}` to memory's `outcomes` list
- [ ] Creates `outcomes` list if not present on memory
- [ ] Returns confirmation string with outcome summary (total outcomes, positive/negative counts)
- [ ] Returns error string if memory_id not found
- [ ] Returns error string if result not in `VALID_OUTCOME_RESULTS`
- [ ] Uses `_atomic_write_yaml()` for safe writes
- [ ] Works for memories in any status (active, decayed, superseded, etc.)

**Technical Notes:**
- Reuse `_find_memory_by_id()` pattern from `reinforce_memory()`
- `ts` auto-set to `date.today().isoformat()`
- Omit `pr` and `context` keys from outcome dict if not provided (keep YAML clean)

**Test Requirements:**
- [ ] Unit: track_outcome adds outcome to memory with existing outcomes
- [ ] Unit: track_outcome creates outcomes list on memory without one
- [ ] Unit: track_outcome rejects invalid memory_id
- [ ] Unit: track_outcome rejects invalid result type
- [ ] Unit: track_outcome handles optional pr and context

**Complexity:** S
**Depends On:** Story 1.1

---

## Epic 2: Learning Review Integration

**Goal:** `learning_review()` ranks proposals by outcome quality and displays outcome stats.
**Dependencies:** Epic 1 (needs constants and schema).

### Story 2.1: Add `_compute_outcome_score()` function

**As a** `learning_review()` consumer
**I want** a Laplace-smoothed outcome score per memory
**So that** proposal ranking accounts for outcome quality with appropriate confidence

**Acceptance Criteria:**
- [ ] Function returns `(adjusted_score, positive_count, scoreable_count)`
- [ ] Laplace formula: `(positive + 1) / (scoreable + 2)`
- [ ] `scoreable` excludes `closed` outcomes (only counts positive + negative)
- [ ] Memory with no outcomes returns `(0.5, 0, 0)`
- [ ] Memory with only `closed` outcomes returns `(0.5, 0, 0)`

**Test Requirements:**
- [ ] Unit: no outcomes → (0.5, 0, 0)
- [ ] Unit: 1/1 positive → (0.67, 1, 1)
- [ ] Unit: 0/1 positive → (0.33, 0, 1)
- [ ] Unit: 4/5 positive → (0.71, 4, 5)
- [ ] Unit: outcomes with only 'closed' → (0.5, 0, 0)
- [ ] Unit: mixed outcomes (positive + negative + closed) → correct score excluding closed

**Complexity:** S
**Depends On:** Story 1.1

---

### Story 2.2: Modify `learning_review()` to rank and display outcomes

**As a** user reviewing learning proposals
**I want** proposals ranked by outcome score with outcome stats displayed
**So that** I can make informed decisions about which patterns to promote

**Acceptance Criteria:**
- [ ] Pattern candidates sorted by `adjusted_score` DESC, tiebreak by `times_reinforced` DESC
- [ ] Each proposal block shows: `**Outcomes:** X/Y positive (score: Z)` when outcomes exist
- [ ] Each proposal block shows: `**Outcomes:** No outcome data` when no outcomes
- [ ] Rollback candidates also display outcome stats
- [ ] Existing learning_review() output format preserved (new fields are additive)

**Technical Notes:**
- Modify the pattern_candidates section of learning_review()
- Call `_compute_outcome_score()` per candidate
- Sort before generating markdown output
- Add one line per proposal for outcome display

**Test Requirements:**
- [ ] Integration: learning_review() with 2+ candidates ranks by outcome score
- [ ] Integration: proposal output includes outcome stats when outcomes exist
- [ ] Integration: proposal output shows "No outcome data" when no outcomes
- [ ] Integration: existing memories without outcomes produce unchanged output format

**Complexity:** M
**Depends On:** Story 2.1

---

## Epic 3: Capture Support

**Goal:** Remind the agent to track outcomes after PR activity.
**Dependencies:** None (advisory message only, doesn't call track_outcome itself).

### Story 3.1: Add outcome reminder to `memory-check.py`

**As an** agent finishing a session with PR activity
**I want** a reminder to track outcomes for relevant memories
**So that** outcomes actually get recorded (explicit-only needs nudges)

**Acceptance Criteria:**
- [ ] Scans transcript for PR activity patterns (gh pr merge, PR merged, etc.)
- [ ] Scans transcript for `track_outcome` calls
- [ ] If PR activity found but no track_outcome calls → show advisory reminder
- [ ] Reminder suggests example `track_outcome()` call
- [ ] Never blocks — always returns `{"continue": True}`
- [ ] No false positives from casual mentions of "merge" in conversation

**Technical Notes:**
- Add `_check_outcome_tracking()` function to `memory-check.py`
- Use regex patterns on `CLAUDE_TRANSCRIPT` (same pattern as `completion-checklist.py`)
- Match invocation patterns (e.g., `gh\s+pr\s+merge`) not bare words
- Call from existing `main()` flow, append to messages list

**Test Requirements:**
- [ ] Unit: transcript with PR merge + no track_outcome → reminder shown
- [ ] Unit: transcript with PR merge + track_outcome → no reminder
- [ ] Unit: transcript without PR activity → no reminder

**Complexity:** S
**Depends On:** None

---

## Epic 4: Testing

**Goal:** Comprehensive test coverage for all new functionality.
**Dependencies:** Epics 1-3 (tests verify the implementations).

### Testing Infrastructure

All tests use existing patterns — no new test infrastructure needed:
- **Fixture:** `tmp_memory` from `conftest.py` (monkeypatches path functions, creates temp memory dirs)
- **Helper:** `_create_memory()` writes YAML files directly with configurable overrides
- **Hook tests:** `importlib.import_module("memory-check")` + `patch.object()` for mocking
- **Assertions:** Return string checks + direct YAML file verification

### Story 4.1: Unit tests for schema, tool, and scoring

**As a** maintainer
**I want** unit tests covering validation, track_outcome, and scoring
**So that** regressions are caught

**Acceptance Criteria:**
- [ ] All test cases below implemented
- [ ] Tests pass with `pytest`
- [ ] No changes to existing passing tests

**Test Cases — Schema Validation (extend `TestSchemaValidation` in `test_memory.py`):**
- [ ] `test_schema_accepts_valid_outcomes` — memory with well-formed outcomes list passes
- [ ] `test_schema_accepts_no_outcomes` — existing memory without outcomes field passes
- [ ] `test_schema_rejects_invalid_outcome_result` — bad result type caught
- [ ] `test_schema_rejects_outcome_missing_ts` — missing timestamp caught
- [ ] `test_schema_rejects_outcomes_not_list` — non-list outcomes field caught

**Test Cases — `track_outcome()` (new `TestTrackOutcome` class in `test_memory.py`):**
- [ ] `test_track_merged_outcome` — appends outcome, verify YAML has result + pr + ts
- [ ] `test_track_creates_outcomes_list` — memory without outcomes field gets list created
- [ ] `test_track_appends_to_existing` — memory with existing outcomes gets new one appended
- [ ] `test_track_invalid_memory_id` — returns `"Error: ... not found"`
- [ ] `test_track_invalid_result` — returns `"Error: Invalid result"`
- [ ] `test_track_omits_optional_fields` — when pr/context not provided, keys absent from YAML
- [ ] `test_track_works_on_decayed_memory` — outcomes are historical facts, works on any status
- [ ] `test_track_positive_feedback` — user feedback result type works

**Test Cases — `_compute_outcome_score()` (new `TestOutcomeScoring` class in `test_memory.py`):**
- [ ] `test_no_outcomes` — returns (0.5, 0, 0)
- [ ] `test_one_positive` — (2/3, 1, 1) — Laplace smoothing, NOT 1.0
- [ ] `test_one_negative` — (1/3, 0, 1)
- [ ] `test_all_positive` — (n+1)/(n+2) for various n
- [ ] `test_mixed_outcomes` — correct Laplace ratio
- [ ] `test_closed_excluded` — `closed` not counted as positive or negative
- [ ] `test_only_closed` — (0.5, 0, 0) — no scoreable outcomes
- [ ] `test_ten_of_ten` — score > 0.9 but < 1.0 (approx 11/12)
- [ ] `test_empty_outcomes_list` — explicit `[]` treated same as absent

**Complexity:** S
**Depends On:** Stories 1.1, 1.2, 2.1

---

### Story 4.2: Integration tests for learning_review and reminder hook

**As a** maintainer
**I want** integration tests verifying learning_review() ranking + display and reminder hook
**So that** the full pipeline is verified end-to-end

**Acceptance Criteria:**
- [ ] All test cases below implemented
- [ ] Tests pass with `pytest`

**Test Cases — learning_review() with outcomes (extend `TestLearningReview` in `test_memory.py`):**
- [ ] `test_learning_review_ranks_by_outcome_score` — memory with 4/5 positive ranks above memory with 1/5, even if latter has higher reinforcement
- [ ] `test_learning_review_shows_outcome_stats` — output includes positive/total ratio for memories with outcomes
- [ ] `test_learning_review_shows_no_outcome_data` — output includes "No outcome data" for memories without
- [ ] `test_learning_review_tiebreak_by_reinforcement` — two memories with no outcomes: higher reinforcement ranks first
- [ ] `test_learning_review_mixed_outcomes_and_no_outcomes` — correct ordering when some memories have outcomes and some don't

**Test Cases — Outcome reminder hook (extend `TestMain` in `test_memory_check.py`):**
- [ ] `test_pr_activity_no_tracking_shows_reminder` — transcript has "gh pr merge" but no "track_outcome" → message suggests tracking
- [ ] `test_pr_activity_with_tracking_no_reminder` — transcript has both → no outcome reminder
- [ ] `test_no_pr_activity_no_reminder` — transcript without PR signals → no outcome reminder
- [ ] `test_reminder_combined_with_existing` — outcome reminder appears alongside existing /reflect and /harvest suggestions

**Complexity:** S
**Depends On:** Stories 2.2, 3.1

---

## Dependency Graph

```
Story 1.1 (constants/validation)
  ├── Story 1.2 (track_outcome tool)
  ├── Story 2.1 (scoring function)
  │     └── Story 2.2 (learning_review integration)
  │           └── Story 4.2 (integration tests)
  └── Story 4.1 (unit tests) ← also depends on 1.2, 2.1

Story 3.1 (reminder hook) ← independent, parallel with everything
```

---

## Implementation Order

1. **Phase 1** (foundation): Story 1.1, Story 3.1 (parallel — independent)
2. **Phase 2** (core): Story 1.2, Story 2.1 (parallel — both depend only on 1.1)
3. **Phase 3** (integration): Story 2.2
4. **Phase 4** (verification): Story 4.1, Story 4.2 (parallel)

**Can be built in 2-3 focused sessions. Single PR.**

---

## Definition of Done

A story is complete when:
- [ ] All acceptance criteria pass
- [ ] Unit tests written and passing
- [ ] No new linter warnings (`ruff check .` clean)
- [ ] Existing tests still pass
- [ ] Documentation updated (if user-facing — applies to track_outcome tool description)
