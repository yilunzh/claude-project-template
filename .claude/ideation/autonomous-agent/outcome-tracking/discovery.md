# Discovery: Outcome Tracking (Gap 3)

## Status: COMPLETE
## Last Updated: 2026-02-16
## Track: B (Musk 5-Step)

## Problem Statement

The Memory MCP captures *behavioral learnings* (corrections, preferences, patterns) but nothing about *outcomes* — did the code we shipped actually work? Were PRs merged or reverted? Did deployments succeed or cause incidents?

Without outcome tracking:
- The self-improvement loop can't distinguish successful patterns from repeated mistakes
- A memory reinforced 5x because the agent keeps making the same error looks identical to one reinforced 5x because it guides correct behavior
- Trust scoring (Gap 5) has no data to compute from
- The agent can't learn which approaches lead to shipped, working software vs. which lead to reverts

**Acuteness:** Minor friction — noticed during learning review / reflection. Not critical yet, but the signal gap is real and grows with the memory base.

## Current State

What exists today:
- **Memory MCP**: Full lifecycle for behavioral memories (capture → reinforce → decay → promote). Has `type`, `scope`, `signal`, `reinforcement_count`, `confidence` fields.
- **`hook-metrics.jsonl`**: Logs hook invocations with timestamps, durations, outcomes (pass/fail). Raw data about process adherence. **Redesign designed** — see `metrics-infrastructure.md` for tiered replacement architecture (`agent-state.json` + `agent-summaries.jsonl`).
- **CI pipeline**: GitHub Actions runs tests + lint on every PR. Status is available via `gh` CLI.
- **Claude review workflows**: `claude-review.yml` and `security-review.yml` post comments on PRs. Feedback exists but isn't captured.
- **Git history**: Commits, merges, reverts are all in git. Can be queried.
- **Metrics infrastructure design** (new): Deep analysis of current metrics system (282KB/20h, 48% skip waste, O(n) queries). Tiered architecture proposed with `agent-state.json` for O(1) runtime queries and `agent-summaries.jsonl` for historical analytics. Namespaced to support hooks, outcomes, and trust scoring in shared files. See `metrics-infrastructure.md`.

What's missing:
- No link between a memory/task ID and its real-world outcome (merged? reverted? incident?)
- No `outcome` field on memory entries
- No `track_outcome()` MCP tool
- No automated outcome detection (merge/revert/incident events)
- `learning_review()` doesn't weight by outcome success rate

## Target Users

- **Memory MCP's learning_review()**: Only existing consumer. Needs outcome data to weight proposals correctly. Currently works but can't distinguish good patterns from bad.
- **Trust scorecard (Gap 5)**: Future consumer. Computed from aggregate outcomes. Not built yet.
- **Human developers**: Want to see "what actually worked?" in their project history. Can already use `git log` / `gh`.
- **Harvester pipeline**: Cross-project promotion should favor patterns with positive outcomes. Not outcome-aware yet.

## "Why" Chain

1. **Why track outcomes?** → To distinguish successful patterns from failing ones
2. **Why not just use reinforcement count?** → High reinforcement = high frequency, not high success. An agent might repeatedly try a failing approach.
3. **Why link to memory entries?** → Enables outcome-weighted learning: "this correction led to 5 successful merges" vs. "this correction was ignored 3 times"
4. **Why automate detection?** → Manual outcome logging won't happen consistently. Events like PR merge/revert are observable.
5. **Fundamental truth**: Learning systems without outcome feedback optimize for repetition, not for success. Outcomes close the loop.

## Subtraction Check

- **What existing complexity surrounds this problem?** The metrics infrastructure design (metrics-infrastructure.md) proposes a 17-file refactor with shared namespaced storage as a prerequisite. That's added complexity, not subtraction.
- **Would removing something solve it without building anything?** Considered removing reinforcement_count (misleading proxy), removing automatic reinforcement (reduce noise), and removing learning_review() proposals (stop pretending to know quality). None address the fundamental gap — the problem is caused by missing data, not by something that exists.
- **What's the simplest possible intervention?** Add an `outcomes` list directly to memory YAML entries + a `track_outcome()` MCP tool. ~3-5 files, ~100 lines. Skip the shared metrics infrastructure — it solves a different problem (hook metrics performance).
- **Verdict:** Nothing to subtract. The gap is real. Build minimally.

## Key Decisions (from discovery interview)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Outcome definition boundary | PR outcomes + explicit user feedback | Clean observable signals from both automated and human channels. No noisy inference from CI/tests. |
| D2 | Outcomes vs reinforcement interaction | Complement — two separate signals | Reinforcement = frequency, outcomes = quality. Combined in learning_review() with adaptive weighting. Neither replaces the other. |
| D3 | Attribution mechanism | Explicit only (to start) | Agent or user names specific memory IDs. Zero noise. Low coverage accepted — fall back to reinforcement for memories without outcomes. Session inference additive later if needed. |
| D4 | Outcome granularity | Binary + separate entries | Each outcome is one of: merged, reverted, closed, positive_feedback, negative_feedback. Regressions tracked as separate negative entries, not quality modifiers. |
| D5 | Solution scope | Outcomes directly in Memory MCP (skip shared infra) | ~3-5 files vs. 17. Co-location eliminates join. Metrics infrastructure is a separate initiative. |

## Research Context

### Industry Patterns
- **Reinforcement Learning**: Reward signals are the foundation. Our equivalent: PR merged = positive reward, reverted = negative reward.
- **A/B Testing platforms**: Track interventions → outcomes. Statistical significance before promoting changes.
- **Incident management (PagerDuty, OpsGenie)**: Link deploys to incidents. Mean Time to Detect, Mean Time to Resolve.
- **GitHub Actions status**: PR checks, deployment status, branch protection — all queryable via `gh api`.
- **EvolveR**: Combines experience replay with outcome evaluation for agent self-improvement.

### Applicable Patterns
- **Event-driven outcome capture**: Hook on PR merge/close → call `track_outcome()` automatically
- **Outcome types taxonomy**: merged, reverted, closed, positive_feedback, negative_feedback — standardized vocabulary
- **Outcome score computation**: successes / total_outcomes per memory entry → 0.0 to 1.0 score
- **Complementary signals**: Reinforcement (frequency) + outcomes (quality) combined with adaptive weighting

### What Already Works in Our System
- Memory MCP YAML format is extensible — adding `outcomes` field is straightforward
- `gh` CLI available for querying PR status, merge events, revert detection
- Harvester scripts pattern (argparse, JSON stdout) for any new utility scripts
- Metrics infrastructure design (metrics-infrastructure.md) is available for future hook metrics refactor but NOT a prerequisite

## Assumptions

| Assumption | Evidence | Confidence | To Validate |
|------------|----------|------------|-------------|
| PR merge/revert are the primary outcome signals | Most work flows through PRs in this template | High | May need additional signals for non-PR work |
| Outcomes can be linked to specific memories | Memories have IDs; explicit attribution chosen | High (was Medium) | Simplified by choosing explicit-only attribution |
| Automated detection via git/gh is reliable | `gh pr list --state merged` is well-supported | High | Need to handle edge cases (squash merges, cherry-picks) |
| Outcome data is stable enough to influence learning | PR outcomes are definitive (merged = merged) | High | Incidents may be delayed/disputed |
| Binary outcomes capture enough signal | Regressions handled via separate entries | High (was Low) | Resolved — multiple binary entries per memory accumulate nuanced picture |

## Open Questions (Resolved)

- [x] **Outcome definition**: PR outcomes + explicit user feedback (D1)
- [x] **Granularity**: Binary outcomes per-memory, multiple entries allowed (D4)
- [x] **Linking mechanism**: Explicit attribution — agent or user names memory IDs (D3)
- [x] **Outcome vs reinforcement**: Complement — two separate signals (D2)
- [x] **Partial success**: Binary entries; regressions are separate negative outcomes (D4)
- [x] **Subtraction check**: Nothing to subtract — gap is real

## Open Questions (Deferred to Phase 2)

- [ ] **Automated detection trigger**: How/when does the agent call `track_outcome()`? Post-merge hook? Manual prompt? Session-end reminder?
- [ ] **Score computation**: Simple ratio (successes/total)? Time-decayed? Details for `learning_review()` weighting formula.
- [ ] **Memory MCP schema change**: How to add `outcomes` field without breaking existing memories? Migration needed?
- [ ] **Privacy/scope**: Should outcome data be project-specific or cross-project?
- [ ] **Negative outcome detection**: How to detect reverts? `git log --grep="revert"` vs. GitHub revert PRs vs. manual?

## Dependencies

- **Depends on**: Nothing directly — can track outcomes independent of other gaps
- **Blocks**: Gap 5 (Autonomy Governor needs aggregate outcome data for trust scoring)
- **Related**: Gap 1 (State Machine may trigger outcome capture on phase transitions), Gap 4 (Acceptance Criteria verification is an outcome event)
- **Decoupled from**: Metrics infrastructure refactor (metrics-infrastructure.md) — separate initiative with own justification
