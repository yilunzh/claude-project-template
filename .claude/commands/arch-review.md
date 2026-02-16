---
description: Run an architectural review of the codebase
---

# Architectural Review

First, log this invocation: `.venv/bin/python3 .claude/hooks/_lib/log_command.py "arch-review"`

Analyze the full codebase for structural health issues. Unlike `/self-review` (which checks the current diff), this reviews the overall architecture.

## Scope

Determine what to review:
1. If on a feature branch with changes, focus on changed files AND their surrounding modules
2. If invoked standalone or on main, review the entire `src/` tree
3. Always include the test tree to assess coverage gaps

## Checks

### Module Size & Cohesion
- Flag any source file over 300 lines (excluding imports/comments)
- Flag any directory with more than 10 source files
- Check that each module has a clear single responsibility (look at its imports and exports)

### Dead Code
- Functions/classes defined but never imported or called from outside their file
- Files that exist but are not imported anywhere
- Unused dependencies in pyproject.toml / package.json / requirements.txt

### Performance Patterns
- O(n^2) or worse: nested loops over collections, repeated list scans
- Unbounded operations: no limits on queries or iterations that could grow large
- Missing caching for repeated expensive computations

### Correctness Patterns
- String comparison for values that should be enum/constant comparisons
- Non-atomic file operations (read then write without temp file + rename)
- Missing error handling on I/O operations (file, network, subprocess)
- Mutable default arguments in function signatures

### Test Coverage Distribution
- List all source modules and whether they have corresponding test files
- Flag modules with 0% test coverage (no test file exists)
- Flag test files that exist but have fewer than 3 test functions (thin coverage)

### Import Consistency
- Imports from deleted or renamed modules
- Circular import chains (A imports B imports A)
- Inconsistent import styles within the same module

### Dependency Health
- Dependencies declared but never imported in source
- Dependencies imported but not declared in pyproject.toml / requirements.txt

## Output Format

Present findings as:

### Architectural Review Results

**Health Score**: X/10 (based on severity-weighted findings)

**Critical** (fix before merging):

| Issue | Location | Description |
|-------|----------|-------------|
| Dead code | `src/foo.py:bar()` | Function never called |

**Warning** (fix soon):

| Issue | Location | Description |
|-------|----------|-------------|
| Large module | `src/services/` | 12 files, consider splitting |

**Info** (track for later):

| Issue | Location | Description |
|-------|----------|-------------|
| Thin tests | `tests/test_hooks.py` | Only 2 test functions |

**Recommendation**: Which issues to fix now vs. defer, prioritized by impact.

### Hook & Command Health

If `.claude/hook-metrics.jsonl` exists, read it and include this section:

1. **Invocation summary**: For each hook, count total invocations, group by decision (allow/block/advisory/skip). Present as a table:

| Hook | Total | Allow | Block | Advisory | Skip |
|------|-------|-------|-------|----------|------|

2. **Effectiveness flags**:
   - **Dead hooks**: Registered in `.claude/settings.json` but 0 invocations in the metrics log — may be misconfigured
   - **High-skip hooks**: >80% skip rate — may need tuning or removal (the hook fires but almost always skips)
   - **Low-compliance advisories**: Check compliance entries — if an advisory hook has <20% "followed" rate, it may be noise rather than useful guidance

3. **Compliance summary**: For hooks with `event: "compliance"` entries, summarize follow rates:

| Advisory Hook | Times Fired | Followed | Ignored | Follow Rate |
|--------------|-------------|----------|---------|-------------|

4. **Hook code health**:
   - Check that all hooks import shared functions from `hook_utils.py` (no duplicated detection/counter logic)
   - Flag hooks that don't call `log_metric()` (should be zero after consolidation)
   - Check `settings.json` references match actual hook files on disk

If the metrics file doesn't exist or is empty, note: "No hook metrics data yet. Metrics will accumulate as hooks fire during normal usage."
