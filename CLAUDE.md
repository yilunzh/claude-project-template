# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview <!-- customizable -->

See `BRIEF.md` for the project description and `docs/SPEC.md` for the technical specification.

## Development Workflow <!-- template-managed -->

### Phase 0: BRANCH FIRST (Feature Branches Required)

Before making ANY changes:

1. **Check current branch**: `git branch --show-current`
2. **For new features**: Create feature branch
   ```bash
   git checkout -b feature/<feature-name>
   ```
3. **For bug fixes**: Create fix branch
   ```bash
   git checkout -b fix/<bug-description>
   ```
4. **NEVER commit directly to main** - All changes go through branches → PR

Only small, trivial changes (typo fixes, config tweaks) can go directly to main.

Done when: On a feature/fix branch, not main.

### Merge Requirements

Before merging any PR:
1. All CI checks must pass
2. Wait for checks to complete — do NOT merge while checks are "in progress"
3. If CI fails — fix issues in the branch, push, wait for CI again

### Phase 1: CLARIFY FIRST (Ask Questions Before Coding)

Before writing ANY implementation code, you MUST:

1. **Read related code** - Understand existing patterns
2. **Ask clarifying questions** about:
   - Ambiguous requirements ("Should X also handle Y?")
   - User-facing text (error messages, labels)
   - Edge cases ("What happens if Z?")
   - Scope boundaries ("Does this include W?")
3. **Non-functional requirements** (if not covered in BRIEF.md):
   - Security expectations ("Should all endpoints be rate-limited? What about secrets management?")
   - CI/quality expectations ("Do you want type checking? Coverage thresholds? Security scanning?")
   - Production readiness ("Structured logging? Audit trails? Graceful degradation?")
4. **Wait for answers** - Do NOT assume. Wrong assumptions = rework.

**For features with UI**, also clarify:
- Design inspiration (sites/apps to emulate)
- Visual style (modern, minimal, playful, etc.)
- Component library preference (if any)
- Key screens/interactions to get right

Done when: All ambiguous requirements clarified.

### Phase 2: PLAN (Create Todo List)

After clarification, create a todo list with:
- Implementation steps
- Test steps (which tests to update/add)
- Verification step ("Run tests, confirm passing")

Done when: Todo list created with implementation, test, and verification steps.

### Phase 3: IMPLEMENT (Autonomous Execution)

Now proceed WITHOUT asking for confirmation:
1. Make incremental changes
2. Fix failures immediately
3. Continue to next step

**Checkpoints**: Every 3-5 major edits, update `.claude/session-context.md` with: Current Goal, Decisions Made, Files Modified, What's Next. Hooks remind at 3 edits, insist at 5.

For multi-session work, write `.claude/handoff.md` before ending.

Done when: All implementation steps complete.

### Phase 4: VERIFY

Before saying "done":
1. Run tests - all must pass
2. If user-facing changes: present options for review
3. Mark todo items completed

**For UI changes**, use Playwright to verify: `browser_navigate` → `browser_snapshot` → compare against expectations.

Done when: Tests pass, user-facing changes reviewed, todos marked complete.

### Phase 5: BEFORE CLAIMING DONE

1. **Run tests** — all must pass
2. **Self-review** (if 5+ files changed): Run `/self-review` for structured checklist
3. **Arch review** (if new modules created or 3+ dirs changed): Run `/arch-review` for structural health
4. **Quality check**:
   - Doc alignment: check if CLAUDE.md, README.md reference changed files
   - Dead code: verify functions in changed files are imported/called somewhere
   - Import consistency: no imports from deleted/renamed modules
5. **Present findings** as prioritized gap list to user

**When to skip reviews**: Bug fixes, typo corrections, config changes, pure refactoring (fewer than 3 files).

Done when: Tests pass, gaps presented (or skipped if criteria not met).

## Decision Guidelines <!-- template-managed -->

### ESCALATE (Ask User)
- User-facing changes (UI, messages, outputs)
- API contracts and data formats
- Error messages and notifications
- Visual design decisions
- Security-sensitive changes
- Breaking changes

### AUTONOMOUS (Just Do It)
- Internal refactoring
- Bug fixes with clear solutions
- Test improvements
- Performance optimizations
- Code organization

## CI & Quality Guidelines <!-- template-managed -->

1. **Don't add CI checks the codebase doesn't pass** - Verify existing code passes before adding new checks
2. **Test hooks locally before committing** - Run hook scripts directly to verify they work
3. **Align local hooks with CI** - Pre-commit hook and CI should run the same checks
4. **Keep PRs small and focused** - One logical change per PR when possible

### GitHub Actions Workflows

Three workflows in `.github/workflows/`:

- **`ci.yml`** — Runs `ruff check .` + `pytest` on every PR and push to main. Mirrors what `pre-commit-check.py` does locally. The `test` job is a required status check for merging.
- **`claude-review.yml`** — Claude-powered code review on PRs (quality, bugs, best practices). Posts inline comments.
- **`security-review.yml`** — Claude-powered security review on PRs (OWASP Top 10, secrets, injection). Posts inline comments.
- **`claude.yml`** — Interactive Claude agent triggered by `@claude` mentions in issues, PR comments, and PR reviews.

**Required secret**: `CLAUDE_CODE_OAUTH_TOKEN` must be set in GitHub repo settings (Settings → Secrets → Actions) for the Claude workflows to function.

## Reference Documentation <!-- customizable -->

- `BRIEF.md` - Initial project description (non-technical)
- `docs/SPEC.md` - Technical specification (grows with project)
- `docs/PATTERNS.md` - Architectural patterns reference

## Hooks <!-- template-managed -->

Custom hooks are in `.claude/hooks/`:
- `gate-check.py` - **Mixed**: Feature state machine — auto-creates state file on feature branches (advisory), blocks code writes when phase < implement (blocking), suggests phase transitions during work (advisory), enforces transition gates (blocking), auto-transitions phases when conditions are met (plan→implement on progress file, implement→verify when all stories complete)
- `pre-commit-check.py` - **Blocking**: Runs tests + lint; blocks direct commits to main; blocks commits when phase < implement
- `branch-check.py` - **Blocking**: Prevents edits on main branch
- `uncommitted-changes-check.py` - **Advisory**: Warns about uncommitted changes at session start (runs on first user prompt)
- `checkpoint-reminder.py` - **Advisory**: Reminds to checkpoint every 3-5 edits; validates checkpoint sections and resets step counter when `session-context.md` is written; shows current feature phase
- `completion-checklist.py` - **Blocking**: Ensures tests were run before session ends; blocks if phase < verify with commits
- `session-handoff.py` - **Blocking**: Detects incomplete work, requires handoff
- `spec-update-check.py` - Triggers SPEC.md updates on key phrases
- `self-review-reminder.py` - **Advisory**: Reminds to run `/self-review` (5+ files changed) and `/arch-review` (new modules, cross-cutting changes, large files)
- `pre-flight-check.py` - **Advisory**: Validates environment setup on first prompt (venv, dependencies)
- `memory-check.py` - **Advisory**: Reminds to capture learnings + surfaces harvest candidates at session end

## Custom Skills <!-- template-managed -->

Custom slash commands are in `.claude/commands/`. See `example.md` for the format.

### Quick Reference: Commands

| Command | When to use | What it does |
|---------|-------------|--------------|
| `/init-project` | Creating a new project | Copies template, bootstraps sync baseline, sets up env |
| `/test-and-commit` | Ready to commit | Runs tests, commits only if passing |
| `/commit-push-pr` | Ready for PR | Commits, pushes, creates PR with summary |
| `/self-review` | After significant work (5+ files) | Structured review checklist before claiming done |
| `/arch-review` | After structural changes | Codebase health: module size, dead code, coverage gaps |
| `/reflect` | End of session | Captures corrections, preferences, patterns to memory |
| `/harvest-learnings` | When harvest candidates exist | Extracts and classifies learnings for cross-project promotion |
| `/web-verify` | After UI changes | Playwright verification of web routes |
| `/sync-templates` | Discovered workflow improvements | Analyzes project for improvements to propagate to templates |
| `/autonomous-implement` | After ideation is complete | Reads implementation plan, implements stories, tests, verifies, creates PR |

## Agent Memory <!-- template-managed -->

The memory MCP server (`src/memory_mcp/`) provides self-improving behavioral memory across sessions.

### Memory Systems

Two memory systems exist. Use the right one:

- **Memory MCP** (`.claude/memory/*.yaml`) — **Default for all learning capture.** Structured lifecycle (active → pattern_candidate → promoted), feeds the harvester pipeline for cross-project promotion. Use `capture_memory()` for corrections, preferences, patterns.
- **Auto memory** (`~/.claude/projects/.../memory/`) — **Curated stable reference only.** Loaded into system prompt automatically. Use for confirmed environment facts, stable patterns validated across sessions, and quick-reference notes. Do NOT capture new learnings here — they won't feed the harvester.

When reflecting or capturing learnings, ALWAYS use memory MCP tools.
When a memory MCP entry gets promoted and is important enough for instant system-prompt access, add a one-liner to auto memory as a "graduated" reference.

### When to Capture

- When the user explicitly corrects you, call `capture_memory(type="correction", signal="explicit_correction", ...)`
- When the user states a preference about output format, naming, or workflow, call `capture_memory(type="preference", signal="explicit_preference", ...)`
- Set `scope` carefully: `universal` for always-applicable, `domain` for domain-specific, `investigation` for session-only, `one_time` for context-specific corrections

### When to Load

- At the start of a new task or investigation, call `load_relevant_memories(domain=<detected>)`
- When first working with a new table/data source, call `load_relevant_memories(tables=<table_name>)`
- When entering a new project phase, call `load_relevant_memories(phase=<phase_name>)`

### How to Use Loaded Memories

- Treat memories as supplementary context, not authoritative rules
- If a memory contradicts a rule, follow the rule
- When a memory influences your behavior, cite it inline: `[Memory: <memory-id>, <count>x]`

### Reflect Command

When the user says "reflect", "session review", or "capture learnings":

1. Review the entire conversation for uncaptured corrections/preferences/patterns
2. Call `capture_reflection()` with what went well and what could improve
3. Call `learning_review()` to generate the session summary and proposals
4. Present the review; wait for user response on proposals
5. If user approves a proposal, call `apply_proposal()` with approved details

### Memory Hierarchy

1. CLAUDE.md rules (highest authority) -- always follow
2. Memory MCP corrections -- personal behavioral guidance (structured, lifecycle-managed)
3. Memory MCP preferences -- style/format, not analysis decisions
4. Auto memory -- stable reference facts (environment, confirmed patterns)

## SPEC.md Updates <!-- template-managed -->

After completing a feature, trigger docs updates by saying:
- `/spec-update`, "feature complete", "update spec", "update documentation"

The Stop hook gathers context (git changes, plan) and prompts for documentation updates.

You can also manually update `docs/SPEC.md`:
- Add feature to "Implemented" section
- Document key architectural decisions
- Update "Current State" as needed
