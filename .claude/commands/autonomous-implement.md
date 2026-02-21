---
description: Autonomously implement from an ideation plan — reads stories, implements, tests, verifies, creates PR
---

# Autonomous Implement

Orchestrate the full implementation loop from an existing implementation plan. Zero human prompts needed between start and PR creation.

## Resumption Check

1. Check if `.claude/implementation-progress.md` exists.
2. If it exists → this is a **resumption**. Read it, then skip to **Step 4** (Execute Story Loop), starting from the first incomplete story.
3. If it does not exist → continue to Step 1.

## Step 1: Locate Implementation Plan

Scan for the implementation plan in priority order:
1. `.claude/ideation/*/implementation-plan.md` — pick the most recently modified
2. `docs/implementation-plan.md`

If no plan found, stop and report: "No implementation plan found. Complete ideation first."

Read the plan fully. Extract:
- **Feature name** (from the plan's title or parent directory name)
- **Stories** with their IDs, titles, acceptance criteria, dependencies, and technical notes
- **Implementation order** (the plan's recommended sequence)
- **Definition of Done** section (for final verification)

## Step 2: Branch Setup

1. Check current branch with `git branch --show-current`
2. If already on a `feature/` or `fix/` branch, use it
3. If on `main`, create and switch to `feature/<feature-name>` (derived from the plan)

## Step 3: Initialize Progress File

Create `.claude/implementation-progress.md` by extracting stories from the plan:

```markdown
# Implementation Progress
## Source: <path-to-implementation-plan>
## Started: <ISO timestamp>
## Current Phase: <first phase name from plan>

## Completed
(none yet)

## In Progress
(none yet)

## Remaining
- [ ] E1.S1 — <title>
  - Acceptance: <criteria count> criteria
  - Depends: <dependencies or "none">
- [ ] E1.S2 — <title>
  ...

## Blockers
(none)
```

Set phase to `implement` in `.claude/feature-state.yaml` if not already there.

## Step 4: Execute Story Loop

For each story in implementation order (from the plan, tracked in progress file):

### 4a. Pick Next Story
- Read `.claude/implementation-progress.md` (re-read on each iteration — this is your checkpoint)
- Find the first incomplete story in the **Remaining** section
- If all stories are complete, go to **Step 5**
- Move it to **In Progress** section in the progress file

### 4b. Implement the Story
- Look up the story's full acceptance criteria and technical notes in the implementation plan (read-only — never modify the plan)
- Write the implementation code
- Write tests for the story
- Run tests with `pytest` (or appropriate test runner)
- If tests fail: fix and re-run (retry once with a different approach)
- If still failing: log blocker in progress file, move story back to Remaining with a `Blocker:` note, skip to next unblocked story

### 4c. Update Progress
- Mark each acceptance criterion as complete in the progress file
- When all criteria pass, move story from **In Progress** to **Completed**
- Update the progress file on disk after each story

### 4d. Phase Commits
- After completing all stories in a phase/epic, commit:
  ```
  feat(<feature-name>): complete <Phase/Epic name>
  ```
- Use separate git commands (never chain with &&)

### 4e. Blocked Story Recovery
- After completing all non-blocked stories, revisit blocked stories
- Try again with fresh context (re-read the error, try alternative approach)
- If still blocked after retry, leave in Remaining with blocker note

## Step 5: Final Verification

When all stories are complete (or all remaining are blocked):

1. Run full test suite: `pytest` (or detected test runner)
2. Run linter: `ruff check .` (or detected linter)
3. Check the implementation plan's **Definition of Done** section:
   - For each DoD item, verify it's satisfied
   - Run any commands mentioned in the DoD (e.g., backtick-wrapped commands)
   - Check file existence requirements
4. Update progress file with verification results

If verification fails, fix issues and re-verify.

## Step 6: Ship

1. Stage all relevant files (avoid .env, credentials, large binaries)
2. Create final commit if there are uncommitted changes
3. Set phase to `verify` in `.claude/feature-state.yaml`
4. Push branch to remote: `git push -u origin <branch-name>`
5. Create PR using `gh pr create` with:
   - Title: short summary of the feature
   - Body: Summary bullets from the implementation plan + test results
6. Report PR URL and summary of what was implemented

## Key Principles

- **Implementation plan is read-only.** Never modify it. It's the design spec.
- **Progress file is execution state.** Update it constantly. It survives context compression.
- **Re-read progress file** at the start of each story. This is how you recover from context compression or session resumption.
- **Commit per phase/epic.** Not per story (too noisy) or at the end (too risky).
- **Skip blocked stories.** Don't get stuck. Come back to them after completing everything else.
- **Never chain git commands with `&&`.** Use separate Bash tool calls.
