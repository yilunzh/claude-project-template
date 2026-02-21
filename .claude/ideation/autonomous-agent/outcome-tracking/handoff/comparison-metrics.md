# Comparison Metrics: Outcome Tracking (Gap 3)

## Track: B (Musk 5-Step)

| Metric | Value | Notes |
|--------|-------|-------|
| Requirements proposed | 14 | Initial enumeration |
| Requirements deleted | 6 (43%) | R9, R11-R14 deleted; R10 reinstated → 5 final deletions (36%) |
| Reinstatement rate | 1 / 6 (17%) | R10 (post-merge reminder) reinstated — explicit-only needs nudges |
| Final requirement count | 9 | 8 core + 1 reinstated |
| Final feature count | 7 user stories | Across 4 epics |
| Architecture layers | 1 | All changes in Memory MCP tool module |
| Estimated LOC (new) | ~150 | New functions + constants |
| Estimated LOC (modified) | ~50 | Validation + learning_review changes |
| Files modified | 4 | memory.py, memory-check.py, test file, possibly _registry (if needed) |
| Files created | 0 | Modification-only build |
| Components/abstractions | 3 | track_outcome tool, _compute_outcome_score, reminder check |
| Test cases | ~27 | 22 unit + 5 integration, across test_memory.py and test_memory_check.py |
| Session count | 3 | Discovery (prior) + requirements/design/architecture (this session) + gap-filling (this session) |
| Subjective quality | TBD | User rating after implementation |
| Time to complete (ideation) | 2 sessions | Discovery → handoff |

## Key Musk 5-Step Outcomes

### What Got Deleted (and stayed deleted)
- Separate outcome query tool (redundant with learning_review)
- Time-decayed scoring (premature — need 20+ outcomes per memory first)
- Duplicate prevention (negligible impact)
- Cross-project aggregation (no consumer)
- Automated revert detection (contradicts explicit-only)

### What Got Challenged and Changed
- **Combined scoring formula**: Original blending formula was challenged during architecture review. Replaced with Laplace smoothing — simpler, handles small samples better, one line of code vs. multi-parameter formula.
- **Metrics infrastructure coupling**: The 17-file refactor was permanently decoupled, not deferred. Outcome tracking and hook metrics serve different consumers via different storage.

### What Got Reinstated
- **Post-merge reminder (R10)**: Deleted because it contradicts explicit-only attribution. Reinstated because explicit-only won't happen without nudges. Reframed as advisory nudge, not automation.

### Scope Reduction from Original Vision
- Original metrics-infrastructure.md proposed: 17 files, tiered storage, namespaced state, dual-write migration, session flush pattern
- Final outcome tracking: 4 files, memory YAML storage, no infrastructure, no migration
- **Scope reduction: ~75%** by questioning the coupling between hook metrics and outcome tracking
