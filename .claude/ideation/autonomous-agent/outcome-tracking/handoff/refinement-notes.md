# Refinement Notes: Outcome Tracking

## What Needs Human Polish

### 1. Reminder Hook Patterns (Story 3.1)
The proposed regex patterns for detecting PR activity in transcripts are untested against real session transcripts. After implementation:
- Run 2-3 sessions with PR activity
- Check if reminder fires correctly (no false positives, no misses)
- Adjust patterns if needed

### 2. learning_review() Output Wording
The exact format of outcome display ("3/4 positive, score: 0.71") is a first draft. Consider:
- Is "score" meaningful to users, or should it just show the ratio?
- Should the Laplace-adjusted score be shown, or just raw positive/total?
- Should memories with negative outcome scores get a visual warning (bold, prefix)?

### 3. learning_review() Internal Refactoring
The current function builds markdown sequentially. Adding sorting by adjusted_score requires:
- Collecting all candidates with their scores FIRST
- Sorting
- THEN generating markdown

This may require reorganizing the function's internal flow. Not hard, but the current code structure might fight it slightly.

## Post-Implementation Monitoring

### Week 1-2: Capture Rate
- How many outcomes are being tracked per session?
- Is the reminder hook firing appropriately?
- If <10% of PRs get outcomes tracked, consider reinstating automated capture

### Week 3-4: Scoring Quality
- Does the Laplace smoothing produce sensible rankings?
- Are memories with negative outcomes actually ranking lower?
- Is the +1/+2 pseudocount appropriate, or should it be +2/+4 (more conservative)?

### Ongoing: Schema Growth
- Monitor YAML file sizes for memories with many outcomes
- If a memory exceeds 50 outcomes, consider adding a cap (drop oldest)

## Deferred Items (Not Forgotten)

| Item | Trigger for Revisiting |
|------|----------------------|
| Session-inferred attribution | If outcome capture rate <10% after 3+ weeks |
| Time-decayed scoring | If individual memories have 20+ outcomes |
| Cross-project outcome sharing | When harvester pipeline is outcome-aware |
| Automated revert detection | If reverts are regularly missed |
| `get_outcome_summary()` tool | If users frequently want per-memory stats outside learning_review |
