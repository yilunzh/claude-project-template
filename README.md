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
│   ├── hooks/               # Quality enforcement scripts
│   │   ├── pre-commit-check.py
│   │   ├── branch-check.py
│   │   ├── uncommitted-changes-check.py
│   │   ├── post-edit-verify.py
│   │   ├── checkpoint-reminder.py
│   │   ├── checkpoint-validator.py
│   │   ├── completion-checklist.py
│   │   ├── session-handoff.py
│   │   └── spec-update-check.py
│   ├── commands/            # Custom slash commands
│   │   └── example.md
│   └── agents/              # Custom subagents
│       ├── test-first.md
│       └── design-review.md
├── CLAUDE.md                # Development workflow
├── BRIEF.md                 # Project description (you edit this)
├── docs/
│   ├── SPEC.md              # Technical spec (grows with project)
│   └── PATTERNS.md          # Architectural patterns reference
├── .gitignore               # Multi-language patterns
└── README.md                # This file
```

## Hooks

The template includes 9 hooks that enforce the development workflow:

| Hook | Type | Purpose |
|------|------|---------|
| `pre-commit-check.py` | Blocking | Runs tests + lint, blocks commits to main |
| `branch-check.py` | Blocking | Prevents editing files on main branch |
| `uncommitted-changes-check.py` | Advisory | Warns about uncommitted changes at session start |
| `post-edit-verify.py` | Advisory | Reminds to run tests after edits |
| `checkpoint-reminder.py` | Advisory | Reminds to checkpoint every 3-5 edits |
| `checkpoint-validator.py` | Advisory | Validates checkpoint sections, resets step counter |
| `completion-checklist.py` | Blocking | Ensures tests ran before session ends |
| `session-handoff.py` | Blocking | Detects incomplete work, requires handoff |
| `spec-update-check.py` | Stop | Triggers SPEC.md updates on key phrases |

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

## Customization

### Adding Skills

Create `.claude/commands/your-skill.md`:

```markdown
---
description: What this skill does
---

# Skill Name

Instructions for Claude when this skill is invoked.
```

Invoke with `/your-skill` in Claude Code.

### Adding Patterns

Update `docs/PATTERNS.md` with patterns you learn and want to reuse.

### Project-Specific Config

After Claude scaffolds your project:
- Update `docs/SPEC.md` as the project evolves
- Add project-specific entries to `.gitignore`
- Create project-specific skills in `.claude/commands/`

## Updating the Template

When you improve the workflow in a project:

```bash
# Copy improved files back to template
cp ~/projects/my-project/.claude/hooks/new-hook.py \
   ~/templates/claude-project-template/.claude/hooks/

# Or diff and merge selectively
diff ~/projects/my-project/CLAUDE.md \
     ~/templates/claude-project-template/CLAUDE.md
```

**Don't sync back:**
- Project-specific BRIEF.md content
- Project-specific docs/SPEC.md content
- Project-specific commands

## MCP Servers

The template configures Playwright MCP for visual verification:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"]
    }
  }
}
```

Use Playwright to screenshot and verify UI changes.

## License

MIT - use this template for any project.
