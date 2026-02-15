# Claude Code Project Template

A **framework-agnostic** template for AI-assisted development with Claude Code. Captures proven development workflow patterns without prescribing a specific tech stack.

## What This Is

This template provides:

- **Development workflow** - Branch-first, clarify, plan, implement, verify
- **Quality enforcement hooks** - Automated checks for tests, linting, branch policy
- **Context management** - Checkpoints and handoffs for long sessions
- **Pattern documentation** - Reference for common architectural decisions

## What This Is NOT

- A starter kit with boilerplate code
- A specific tech stack
- A web framework template

**Key insight**: The value isn't in code scaffolding - it's in the AI-assisted development workflow. Let requirements drive technology decisions.

## Getting Started

### 1. Create Your Project

```bash
# Clone template to new project directory
cp -r /path/to/claude-project-template ~/projects/my-new-project
cd ~/projects/my-new-project

# Initialize git (template doesn't include .git)
git init
git add .
git commit -m "Initial commit from claude-project-template"
```

### 2. Describe Your Project

Edit `BRIEF.md` with a non-technical description of what you're building:

- What is it?
- Why build it?
- For whom?
- Key requirements
- Design inspiration (if UI involved)

### 3. Start Building

```bash
# Start Claude Code
claude

# First message:
# "I'm starting a new project. Read BRIEF.md and help me plan the implementation."
```

Claude will:
1. Read your brief
2. Ask clarifying questions
3. Recommend a tech stack
4. Create an implementation plan
5. Start building with the hooks enforcing quality

## Directory Structure

```
claude-project-template/
├── .claude/
│   ├── settings.json        # Hooks + MCP server configuration
│   ├── hooks/               # Quality enforcement scripts (15 hooks)
│   │   ├── _lib/            # Shared hook utilities
│   │   │   └── hook_utils.py
│   │   ├── pre-commit-check.py
│   │   ├── branch-check.py
│   │   ├── uncommitted-changes-check.py
│   │   ├── post-edit-verify.py
│   │   ├── auto-format.py
│   │   ├── checkpoint-reminder.py
│   │   ├── checkpoint-validator.py
│   │   ├── completion-checklist.py
│   │   ├── session-handoff.py
│   │   ├── spec-update-check.py
│   │   ├── implementation-plan-check.py
│   │   ├── memory-flush.py
│   │   ├── self-review-reminder.py
│   │   ├── pre-flight-check.py
│   │   └── harvest-check.py
│   ├── commands/            # Custom slash commands
│   │   ├── commit-push-pr.md
│   │   ├── test-and-commit.md
│   │   ├── web-verify.md
│   │   ├── self-review.md
│   │   ├── reflect.md
│   │   ├── harvest-learnings.md
│   │   ├── sync-templates.md
│   │   └── example.md
│   ├── scripts/
│   │   └── harvester/       # Learning harvest pipeline
│   │       ├── extract_terms.py
│   │       ├── diff_candidates.py
│   │       └── classify.py
│   ├── agents/              # Custom subagents
│   │   ├── test-first.md
│   │   └── design-review.md
│   ├── memory/              # Agent memory (personal, gitignored)
│   │   ├── corrections/     # Behavioral corrections
│   │   ├── preferences/     # User preferences
│   │   ├── patterns/        # Observed workflow patterns
│   │   └── reflections/     # Session reflections
│   └── ideation/            # Structured ideation workflow
│       └── IDEATION_PROCESS.md
├── .github/
│   └── workflows/           # CI and automated review
│       ├── ci.yml
│       ├── claude-review.yml
│       └── security-review.yml
├── src/
│   └── memory_mcp/          # Memory MCP server
│       ├── __init__.py
│       ├── server.py
│       └── tools/
│           ├── __init__.py
│           ├── _registry.py
│           ├── _paths.py
│           ├── _git_helpers.py
│           └── memory.py
├── tests/                   # Test suite
│   ├── conftest.py
│   ├── test_registry.py
│   ├── test_server.py
│   ├── test_memory.py
│   ├── test_hook_utils.py
│   ├── test_completion_checklist.py
│   └── test_harvester.py
├── pyproject.toml           # Python project config (memory MCP)
├── CLAUDE.md                # Development workflow
├── BRIEF.md                 # Project description (you edit this)
├── docs/
│   ├── SPEC.md              # Technical spec (grows with project)
│   └── PATTERNS.md          # Architectural patterns reference
├── .gitignore               # Multi-language patterns
└── README.md                # This file
```

## Hooks

The template includes 15 hooks that enforce the development workflow:

| Hook | Type | Purpose |
|------|------|---------|
| `pre-commit-check.py` | Blocking | Runs tests + lint, blocks commits to main |
| `branch-check.py` | Blocking | Prevents editing files on main branch |
| `uncommitted-changes-check.py` | Advisory | Warns about uncommitted changes at session start |
| `post-edit-verify.py` | Advisory | Reminds to run tests after edits |
| `auto-format.py` | Advisory | Auto-formats Python files with black/isort |
| `checkpoint-reminder.py` | Advisory | Reminds to checkpoint every 3-5 edits |
| `checkpoint-validator.py` | Advisory | Validates checkpoint sections, resets step counter |
| `completion-checklist.py` | Blocking | Ensures tests ran before session ends |
| `session-handoff.py` | Blocking | Detects incomplete work, requires handoff |
| `spec-update-check.py` | Stop | Triggers SPEC.md updates on key phrases |
| `implementation-plan-check.py` | Advisory | Reminds to update implementation plans |
| `memory-flush.py` | Advisory | Reminds to capture session learnings before ending |
| `self-review-reminder.py` | Advisory | Reminds to run `/self-review` after large changes (5+ files) |
| `pre-flight-check.py` | Advisory | Validates environment setup on first prompt |
| `harvest-check.py` | Advisory | Surfaces learning harvest candidates at session end |

### Language Detection

Hooks automatically detect your project type:

- **Python**: pytest, flake8/ruff
- **Node.js**: npm test, eslint
- **Rust**: cargo test, cargo clippy
- **Go**: go test, go vet

## Development Workflow

1. **BRANCH FIRST** - Create feature branch before any changes
2. **CLARIFY** - Ask questions before coding (especially for UI)
3. **PLAN** - Create todo list with implementation steps
4. **IMPLEMENT** - Make incremental changes, checkpoint every 3-5 edits
5. **VERIFY** - Run tests, use Playwright for UI changes

## GitHub Actions & CI

Three workflows run automatically on pull requests:

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `ci.yml` | PR + push to main | Runs `ruff check .` + `pytest`. Required status check for merging. |
| `claude-review.yml` | PR (code files only) | Claude-powered code review — quality, bugs, best practices. Posts inline comments. |
| `security-review.yml` | PR (code files only) | Claude-powered security review — OWASP Top 10, secrets, injection. Posts inline comments. |

**Path filters**: The review workflows only trigger when code files change (`.py`, `.js`, `.ts`, `.yml`, `.yaml`, `.toml`, `.cfg`, `.json`, `.html`, `.css`). Docs-only PRs skip review.

**Required setup**: Add `ANTHROPIC_API_KEY` to GitHub repo settings (Settings → Secrets and variables → Actions) for the Claude review workflows.

**Branch protection**: Configure a ruleset on `main` requiring the `test` status check to pass before merging. This ensures CI + review complete before any merge.

## Session Lifecycle

How the hooks, commands, and workflows fit together across a typical session:

```
Session Start
  ├─ pre-flight-check        → validates venv, dependencies
  └─ uncommitted-changes-check → warns about stale changes

During Work
  ├─ branch-check            → blocks edits on main
  ├─ post-edit-verify        → reminds to test after edits
  ├─ checkpoint-reminder     → nudges every 3-5 edits
  └─ checkpoint-validator    → validates checkpoint sections

Before Commit
  ├─ /test-and-commit        → run tests, commit if passing
  └─ /commit-push-pr         → commit, push, create PR

Pull Request
  ├─ ci.yml                  → lint + tests (required check)
  ├─ claude-review.yml       → code quality review
  └─ security-review.yml     → security review

Session End
  ├─ /reflect                → capture learnings to memory
  ├─ /harvest-learnings      → extract candidates for promotion (if any)
  ├─ memory-flush            → reminds to capture uncaptured learnings
  ├─ harvest-check           → surfaces harvest candidates
  ├─ completion-checklist    → ensures tests were run
  └─ session-handoff         → requires handoff if work is incomplete
```

## Customization

### Built-in Commands

The template includes ready-to-use slash commands:

| Command | Description |
|---------|-------------|
| `/commit-push-pr` | Complete workflow from staged changes to PR creation |
| `/test-and-commit` | Run tests first, only commit if passing |
| `/web-verify` | Playwright verification for web routes |
| `/self-review` | Structured self-review checklist for significant work |
| `/reflect` | Capture session learnings (corrections, preferences, patterns) to memory |
| `/harvest-learnings` | Extract and classify learning candidates for cross-project promotion |
| `/sync-templates` | Analyze project for improvements to propagate to templates |

### Adding Custom Commands

Create `.claude/commands/your-command.md`:

```markdown
# Command Name

Instructions for Claude when this command is invoked.

## Steps
1. Step one
2. Step two
```

Invoke with `/your-command` in Claude Code.

### Ideation Process

For complex features, use the structured ideation workflow in `.claude/ideation/IDEATION_PROCESS.md`. This 7-phase process transforms ideas into implementation-ready packages:

1. **Problem Discovery** - Understand WHY
2. **Solution Definition** - Define WHAT
3. **Design Discovery** - Establish visual language
4. **Design Specification** - Detail HOW it looks
5. **Architecture** - Define HOW it's built
6. **Implementation Planning** - Create development roadmap
7. **Handoff** - Package for implementation

Create feature ideation folders at `.claude/ideation/<feature-name>/` with artifacts from each phase.

### Adding Patterns

Update `docs/PATTERNS.md` with patterns you learn and want to reuse.

### Project-Specific Config

After Claude scaffolds your project:
- Update `docs/SPEC.md` as the project evolves
- Add project-specific entries to `.gitignore`
- Create project-specific commands in `.claude/commands/`

## Syncing Improvements from Projects

As you work on projects, you may discover workflow improvements (new hooks, refined rules, better processes). To propagate these back to the templates:

1. Open the project in Claude Code
2. Run `/sync-templates` or ask "analyze this project for template improvements"
3. Claude will:
   - Compare your project's CLAUDE.md, hooks, commands, and agents against the templates
   - Evaluate each difference for generalizability and value
   - Recommend which improvements should become part of the default templates
   - Apply approved changes to both `claude-project-template` and `cursor-project-template`

No manual logging required - Claude analyzes on demand and you decide what to adopt.

**What might get synced:**
- Workflow patterns that proved useful
- New or improved hooks
- Broadly applicable commands or agents
- Process documentation refinements

**What stays project-specific:**
- BRIEF.md content
- docs/SPEC.md content
- Tech-stack-specific commands

## Agent Memory System

The template includes a self-improving agent memory system that captures behavioral learnings across sessions.

### How It Works

1. **Capture** -- When the user corrects the agent or states preferences, learnings are saved to `.claude/memory/` as YAML files
2. **Load** -- At session start or phase transitions, relevant memories are loaded and scored against the current context
3. **Reinforce** -- When the same correction recurs, the memory is reinforced. After 3+ reinforcements, it becomes a "pattern candidate"
4. **Promote** -- Pattern candidates can be promoted to commands/agents through a review pipeline
5. **Expire** -- Unused memories decay after 60 days and are deleted after 90 days

### Memory Types

| Type | Purpose |
|------|---------|
| Correction | "Don't do X, do Y instead" |
| Preference | "I prefer bullet points over paragraphs" |
| Pattern | "When doing X, always check Y first" |
| Reflection | End-of-session retros (what went well, what to improve) |

### Setup

```bash
pip install -e ".[dev]"
```

The memory MCP server is configured in `.claude/settings.json` and starts automatically.

### Running Tests

```bash
PYTHONPATH=src pytest -v
```

## MCP Servers

The template configures two MCP servers:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"]
    },
    "memory": {
      "command": "python3",
      "args": ["-m", "memory_mcp.server"],
      "env": { "PYTHONPATH": "src" }
    }
  }
}
```

- **Playwright** -- Screenshot and verify UI changes
- **Memory** -- Self-improving agent memory system (capture, load, reinforce, review)

## License

MIT - use this template for any project.
