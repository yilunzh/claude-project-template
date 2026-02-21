# Metrics Infrastructure Design

## Status: PHASE 2 ARTIFACT (Analysis)
## Last Updated: 2026-02-16
## Origin: Metrics redesign deep-dive session, folded into outcome-tracking initiative

---

## 1. Problem Analysis

### The Core Issue

The current `hook-metrics.jsonl` serves **4 conflicting roles** with a single append-only file:

| Role | Query Pattern | What it needs |
|------|--------------|---------------|
| Runtime state ("did tests pass?") | Read latest entry | Last-write-wins field |
| Compliance checking ("which advisories fired?") | Filter today's entries | Indexed/filtered access |
| Analytics ("/arch-review skip rates") | Aggregate all entries | Summarized counters |
| Experiment data (simplification skip rates) | Full history | Raw event log |

One file, mediocre at all four.

### Data Profile (20-hour sample, Feb 15-16 2026)

- **File size**: 282KB (1,644 events)
- **Projected growth**: ~12MB/month, ~150MB/year
- **No rotation**: File grows without bound

### Skip Waste

**791 of 1,644 events are skips (48%)**. Worst offenders:

| Hook | Fires | Skip Rate | Why |
|------|-------|-----------|-----|
| `uncommitted-changes-check` | 92 | 100% | Only matters on first prompt |
| `pre-flight-check` | 92 | 100% | Same pattern |
| `checkpoint-reminder` | 265 | 99.2% | Only 2 meaningful events out of 265 |
| `auto-format` | 75 | 100% | Hook deleted; historical data only |

### Performance

- `last_pytest_passed()` does **O(n) backward scan** through entire JSONL (~1,600 lines, ~20-50ms)
- `check_advisory_compliance()` scans all entries filtered by today's date
- Both queries have O(1) answers if stored differently

### Consumer Mapping

| Consumer | What it reads | Uses skip data? | Current limitation |
|----------|--------------|-----------------|-------------------|
| `last_pytest_passed()` (gate-check) | Scans from end for latest test result | No (skips slow the scan) | O(n) backward scan |
| `check_advisory_compliance()` (memory-check) | Today's `decision="advisory"` entries | No | Must scan all entries |
| `/arch-review` command | Full table: Allow/Block/Advisory/Skip | **Yes** — flags >80% skip as "needs tuning" | Reads entire file |
| Simplification experiment | Skip rate as reversal criterion ("stays >50%") | **Yes** — key metric | Needs full history |
| Ad-hoc analysis | Everything | **Yes** | No aggregation |

---

## 2. Design Framework

### Tiering Decision Function

Two axes determine how to store each event type:

**Axis 1: Consumer Query Type**

| Question type | Example | Right structure |
|--------------|---------|----------------|
| "What's the latest X?" | Did tests pass? | **Last-write-wins field** — overwrite in place |
| "How many times did Y happen?" | Skip rate, block count | **Counter** — increment in place |
| "What exactly happened when Z occurred?" | Why did it block? What transition? | **Capped event list** — append with detail |
| "How are things trending?" | Is skip rate improving? | **Per-session aggregate** — one summary per session |

**Axis 2: Event Volume per Session**

| Volume | Treatment | Rationale |
|--------|-----------|-----------|
| ~1-5 per session (blocks, transitions) | Individual entries with detail | Rare enough that detail matters; you'll want to debug these |
| ~5-20 per session (advisories, test runs) | Counter + names list | Moderate volume; need to know which ones fired, not every detail |
| ~100+ per session (skips, allows) | Counter only | High volume; individual entries add noise, only aggregate useful |

### Applied Tiering

| Event type | Volume/session | Consumer query | Tier |
|-----------|---------------|----------------|------|
| Test result (pass/fail) | ~1-5 | "What's the latest?" | Runtime state: `last_test_result` field |
| Advisory fired | ~5-20 | "Which ones fired?" + compliance check | Runtime state: `advisories_fired` list |
| Block | ~0-5 | "What exactly blocked?" | Notable events (capped list with detail) |
| Phase transition | ~2-5 | "What transitions happened?" | Notable events (capped list with detail) |
| Skip | ~400 | "What's the skip rate?" | Counter only → session summary |
| Allow (non-skip) | ~50-100 | "How often does X act?" | Counter only → session summary |

**Rule**: If you'd ever grep for an individual instance, store it as an event. If you'd only ever count them, store a counter.

### Session Boundary

**Session = process lifetime**, determined by `CLAUDE_SESSION_ID` environment variable.

- New `claude` launch → new session ID
- `/clear` → same process, **same session ID** (clears conversation context, not process)
- Close terminal / Ctrl+C → relaunch → new session ID

Implication: `/clear` doesn't create a session boundary. Work on Topic A, `/clear`, then Topic B → both merge into one session summary. This is acceptable because metrics (skip rates, block rates, compliance) are aggregate — topic boundaries aren't meaningful for hook effectiveness analysis.

### Flush-on-New-Session Pattern

**Why not the Stop hook?** It fires **every turn end** (10-30 times per session), not at session exit. No reliable session-end signal exists.

**Pattern:**

```
Session N:
  Hook fires → counter increments in agent-state.json
  Hook fires → counter increments...
  Stop hook → compliance check runs, results stored
  (user closes terminal — no signal)

Session N+1:
  First hook fires → detects new session ID (mismatch with stored ID)
  → Flush Session N's counters to agent-summaries.jsonl
  → Reset counters for Session N+1
  → Process current hook normally
```

**Benefits:**
- No "session end" detection needed
- Survives unclean exits — data persists in agent-state.json until next session
- One summary per session, guaranteed
- First hook of new session does double duty: flush old + start new

**Tradeoff:** Last session before a long break stays in agent-state.json until next session starts. Unflushed until someone launches `claude` again. Minor consequence.

---

## 3. Proposed Architecture

### File Layout

| File | Purpose | Access pattern |
|------|---------|---------------|
| `agent-state.json` | Runtime state for any agent subsystem | Read-modify-write per hook invocation |
| `agent-summaries.jsonl` | Historical session analytics | Append-only, one line per session |

Names are intentionally generic (`agent-*` not `hook-*`) to support outcome tracking and trust scoring in the same files.

### `agent-state.json` Structure

```json
{
  "hooks": {
    "last_test_result": {
      "passed": true,
      "timestamp": "2026-02-16T21:30:00Z",
      "command": "pytest"
    },
    "session": {
      "session_id": "abc-123-def",
      "counters": {
        "checkpoint-reminder.skip": 18,
        "checkpoint-reminder.allow": 2,
        "branch-check.skip": 127,
        "branch-check.allow": 141,
        "completion-checklist.block": 3
      },
      "advisories_fired": [
        {
          "hook": "checkpoint-reminder",
          "timestamp": "2026-02-16T20:15:00Z",
          "message": "Consider checkpointing — 3 edits since last checkpoint"
        }
      ],
      "notable_events": [
        {
          "hook": "completion-checklist",
          "decision": "block",
          "timestamp": "2026-02-16T21:25:00Z",
          "message": "Tests have not been run this session",
          "detail": "..."
        }
      ]
    }
  },
  "outcomes": {
    "// future: latest PR status, deploy result, etc."
  },
  "trust": {
    "// future: current trust level, score components"
  }
}
```

**Field semantics:**
- `last_test_result` — Last-write-wins. Overwritten on every test run.
- `session.session_id` — Current `CLAUDE_SESSION_ID`. Mismatch triggers flush.
- `session.counters` — Per-hook decision counters. Format: `{hook_name}.{decision}`.
- `session.advisories_fired` — List of advisory events with detail. Useful for compliance checking.
- `session.notable_events` — Capped at 50. Blocks, phase transitions, anything worth debugging individually.

### `agent-summaries.jsonl` Structure

Each line is one session summary with a `type` discriminator:

```json
{"type": "hook_session", "session_id": "abc-123", "ts_start": "2026-02-16T13:00:00Z", "ts_end": "2026-02-16T21:30:00Z", "counters": {"checkpoint-reminder.skip": 92, "branch-check.allow": 268}, "advisory_count": 2, "block_count": 3, "notable_events_count": 5}
```

Future types (extensible via `type` field):

```json
{"type": "outcome", "pr": 123, "result": "merged", "memory_ids": ["abc", "def"]}
{"type": "trust_snapshot", "level": "walk", "scores": {"hook_compliance": 0.85, "outcome_rate": 0.92}}
```

### Compression Math

| Time period | Raw events (current) | Session summaries (proposed) |
|------------|---------------------|------------------------------|
| 20 hours | 282KB (1,644 lines) | ~2KB (4 lines) |
| 1 month | ~12MB est. | ~45KB (~90 sessions) |
| 1 year | ~150MB est. | ~550KB (~1,100 sessions) |

**Compression ratio: ~140x.** A year of summaries is smaller than one day of raw events. No rotation needed.

---

## 4. Research Findings

### Industry References

**Honeycomb** — Three data types: Logs (raw events, "what happened?"), Metrics (aggregated counters, "is it getting worse?"), Traces (request flow). Our single JSONL tries to be both logs and metrics simultaneously. Tiered approach (raw for recent debugging, aggregated for trends) is production standard.

**IBM** — Three pillars of observability (logs, metrics, traces) validate the separation pattern. Different data types serve different queries.

**Pre-commit ecosystem** — GitHub issue #2933 asked for hook performance metrics; closed without implementation. Most hook systems have zero instrumentation. Our project is ahead of the curve.

**Lightweight local telemetry** — SQLite is gold standard for local telemetry but overkill at our scale (~30 sessions/month). Read-modify-write JSON (already used in `.step-counter`) is the right primitive. OpenTelemetry is too heavy for local tooling.

**Tiered retention pattern** — Keep full-resolution data briefly, aggregate for medium term, store only key metrics long-term. Applied: Full resolution = in-session counters (current session only), Medium term = session summaries (last 30+ sessions), Long term = nothing needed at our scale.

---

## 5. Implementation Details

### `hook_utils.py` API

**Core recording function:**

```python
def record_hook_result(hook_name: str, decision: str, message: str = "", detail: dict = None):
    """
    Records hook result in agent-state.json.

    1. Read agent-state.json
    2. Check session_id — if mismatch, flush old session to agent-summaries.jsonl
    3. Increment counter: hooks.session.counters[f"{hook_name}.{decision}"]
    4. If decision="advisory", append to advisories_fired
    5. If decision="block" or phase transition, append to notable_events (cap at 50)
    6. Write back to agent-state.json

    Every hook invocation does JSON read-modify-write (~ms latency).
    """
```

**Session flush (called internally):**

```python
def _flush_session_summary():
    """
    Called when new session ID detected.

    1. Read session counters from agent-state.json
    2. Compute totals (advisory_count, block_count, notable_events_count)
    3. Append one JSON line to agent-summaries.jsonl with type="hook_session"
    4. Reset session counters in agent-state.json
    """
```

**Test result tracking:**

```python
def update_test_result(passed: bool, command: str):
    """Overwrites hooks.last_test_result field. O(1) write."""
```

**Query functions:**

```python
def last_test_passed() -> bool:
    """O(1) read from agent-state.json hooks.last_test_result.passed
    (vs. current O(n) backward scan through JSONL)"""

def check_advisory_compliance() -> list:
    """O(1) read from agent-state.json hooks.session.advisories_fired
    (vs. current scan for decision='advisory' in today's events)"""
```

### Migration Plan

**Dual-write transition** (preserves active simplification experiment data until ~March 15):

1. `record_hook_result()` writes to **both** new `agent-state.json` AND old `hook-metrics.jsonl`
2. Consumers gradually migrate to new API
3. After experiment concludes (~March 15), remove old JSONL writes
4. Delete `hook-metrics.jsonl`

**Why dual-write:** The active hook consolidation experiment (Feb 15 – March 15) reads `hook-metrics.jsonl` for skip rate analysis. Changing format mid-experiment makes before/after comparison impossible. Dual-write ensures experiment data continuity.

**Tradeoff:** Hooks are slower during transition (two write paths), codebase has parallel systems for ~1 month.

### Consumer Updates

Touches **17 files** total. Key consumers:

| Consumer | Current approach | New approach |
|----------|-----------------|--------------|
| `gate-check.py` (`last_pytest_passed()`) | O(n) backward JSONL scan | O(1) `agent-state.json` field read |
| `memory-check.py` (compliance) | JSONL scan for today's advisories | O(1) `advisories_fired` list read |
| `/arch-review` command | Full JSONL table | Merge `agent-summaries.jsonl` history + `agent-state.json` current session |
| Simplification experiment | Raw JSONL skip rates | Continue reading `hook-metrics.jsonl` during dual-write |

**Arch-review merging logic:**
1. Read `agent-summaries.jsonl` — filter by date if needed
2. Sum counters across all session summaries
3. Read `agent-state.json` `hooks.session.counters` (current in-progress session)
4. Add current session counters to historical totals
5. Present combined table

---

## 6. How Outcome Tracking Extends This

### Shared Infrastructure

Hook metrics and outcome tracking are different data, different consumers, different granularity — but share the same **tiered infrastructure pattern**:

| Subsystem | Runtime state (`agent-state.json`) | Historical (`agent-summaries.jsonl`) |
|-----------|-----------------------------------|--------------------------------------|
| Hook metrics | `hooks.last_test_result`, `hooks.session.counters` | `type: "hook_session"` summaries |
| Outcome tracking | `outcomes.last_pr`, `outcomes.pending` | `type: "outcome"` events |
| Trust scoring | `trust.current_level`, `trust.score_components` | `type: "trust_snapshot"` snapshots |

### Design Principles That Transfer

Both subsystems need:
- **O(1) for runtime decisions** (e.g., "did tests pass?" / "what was last deploy status?")
- **Aggregated for analytics** (e.g., "skip rate trend" / "success rate over last 10 PRs")

### Namespacing

```json
{
  "hooks": { "/* metrics infrastructure */" },
  "outcomes": {
    "last_pr": {
      "number": 123,
      "status": "merged",
      "memory_ids": ["abc", "def"]
    }
  },
  "trust": {
    "current_level": "walk",
    "score_components": {
      "hook_compliance": 0.85,
      "outcome_rate": 0.92
    }
  }
}
```

### What Discovery.md Referenced (Now Superseded)

Previously: "Builds on `hook-metrics.jsonl` append-only pattern → same pattern for outcome events"

Now: Outcome tracking builds on the tiered `agent-state.json` + `agent-summaries.jsonl` infrastructure. The append-only JSONL pattern is preserved for historical data, but runtime queries use the state file.

---

## 7. Open Questions (For Continuing Ideation)

### Metrics-Specific

- [ ] **Implementation cost worth it?** Touches 17 files for infrastructure that "works" — could just add rotation (10 lines of code) instead. Counter: rotation solves growth but not the O(n) queries or conflicting consumer needs.
- [ ] **Performance regression?** Every hook does JSON read-modify-write vs. simple append. 268 branch-check fires = 268 parse-modify-serialize cycles. Likely <1ms each, but untested.
- [ ] **Atomic writes?** Proposed temp file + rename for crash safety, but existing `.step-counter` does plain `json.dump()` and has been fine. If state file corrupts, we lose one session's counters (minor).
- [ ] **Mid-session arch-review fragile?** Combining two sources via markdown instructions — agent might get merging wrong.
- [ ] **Notable events cap (50) arbitrary?** 34 completion-checklist blocks in one session would all be notable events. Useful granularity, or should repeated blocks be deduplicated with count?
- [ ] **Solving the right problem?** Maybe the issue is analysis UX (better analysis script, `/metrics-report` command), not storage format.

### Outcome-Tracking Integration

- [ ] **How does `track_outcome()` MCP tool write to `agent-state.json`?** Direct file write? Through hook_utils? Separate utility?
- [ ] **Should outcome events trigger trust score recomputation?** Eager (recompute on every outcome) vs. lazy (recompute on query)?
- [ ] **Linking mechanism between memories and outcomes?** Explicit annotation during capture? Git commit message convention? Both?

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Current file size (20h) | 282KB, 1,644 events |
| Skip rate | 48% (791/1,644) |
| Compression ratio | ~140x with session summaries |
| Summary size (20h) | ~2KB (4 lines) |
| Summary size (1 year) | ~550KB (~1,100 sessions) |
| Files affected by implementation | 17 |
| Notable events cap | 50 |
| O(n) → O(1) improvement | Runtime queries (test result, compliance) |
