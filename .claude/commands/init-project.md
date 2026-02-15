# Initialize New Project from Template

Create a new project from this template with proper sync baseline.

**Run from Claude Code inside the template repo.**

## Usage

```
/init-project <destination-path>
```

**Arguments:**
- `<destination-path>` — Required. Where to create the new project (e.g., `~/projects/my-app`)

The destination path is: $ARGUMENTS

## Steps

### 1. Validate

- Parse the destination path from arguments. If empty, ask the user for a path.
- Expand `~` to `$HOME` if present.
- **Destination must NOT exist** — refuse if it does (don't overwrite).
- **Current directory must be the template repo** — verify `CLAUDE.md` and `.claude/commands/init-project.md` exist.

### 2. Copy project files

Use `rsync` to copy template files to the destination, excluding template-internal artifacts:

```bash
rsync -a \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='.mypy_cache' \
  --exclude='.DS_Store' \
  --exclude='.claude/session-context.md' \
  --exclude='.claude/handoff.md' \
  --exclude='.claude/.step-counter' \
  --exclude='.claude/template-ref' \
  --exclude='.claude/harvest-queue.yaml' \
  --exclude='.claude/settings.local.json' \
  --exclude='.claude/plans' \
  --exclude='.claude/ideation/learning-harvester' \
  --exclude='.claude/ideation/template-push-sync' \
  --exclude='.claude/ideation/template-review-release' \
  --exclude='.claude/memory/corrections/*.yaml' \
  --exclude='.claude/memory/preferences/*.yaml' \
  --exclude='.claude/memory/patterns/*.yaml' \
  --exclude='.claude/memory/reflections/*.md' \
  --exclude='*.egg-info' \
  --exclude='dist' \
  --exclude='build' \
  --exclude='.playwright-verified' \
  --exclude='README.md' \
  ./ <destination>/
```

**Important**: The trailing `/` on both source and destination matters for rsync behavior.

### 3. Bootstrap `.claude/template-ref/`

Create the template-ref directory in the new project with snapshots of template-managed files. These serve as the merge base for future `/sync-templates --reverse` runs.

```bash
mkdir -p <destination>/.claude/template-ref/hooks/_lib
mkdir -p <destination>/.claude/template-ref/commands
mkdir -p <destination>/.claude/template-ref/agents
```

Copy these files from the **template repo** (current directory) into template-ref:

```bash
# Root config
cp CLAUDE.md <destination>/.claude/template-ref/CLAUDE.md
cp .claude/settings.json <destination>/.claude/template-ref/settings.json

# Hooks (all .py files + _lib/)
cp .claude/hooks/*.py <destination>/.claude/template-ref/hooks/
cp .claude/hooks/_lib/*.py <destination>/.claude/template-ref/hooks/_lib/

# Commands (all .md files)
cp .claude/commands/*.md <destination>/.claude/template-ref/commands/

# Agents (all .md files)
cp .claude/agents/*.md <destination>/.claude/template-ref/agents/
```

### 4. Create `meta.yaml`

Gather template version info and write `<destination>/.claude/template-ref/meta.yaml`:

```bash
# Get template version (git commit hash, or "unknown" if not a git repo)
TEMPLATE_VERSION=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

# Get template repo URL (remote origin, or local path as fallback)
TEMPLATE_REPO=$(git remote get-url origin 2>/dev/null || pwd)

# Get today's date
TODAY=$(date +%Y-%m-%d)
```

Write the file:

```yaml
template_repo: <TEMPLATE_REPO>
template_version: <TEMPLATE_VERSION>
last_synced: <TODAY>
```

### 5. Generate README

Derive the project name from the destination path basename. Write `<destination>/README.md`:

```markdown
# <project-name>

Created from [claude-project-template](<TEMPLATE_REPO>).

See `BRIEF.md` for project description.
```

### 6. Initialize git

```bash
cd <destination>
git init -b main
git add .
git commit -m "Initial commit from claude-project-template"
```

### 7. Set up Python environment

The memory MCP server requires Python 3.10+. Find a suitable interpreter before creating the venv.

**Find Python 3.10+:**

```bash
# Try versioned binaries first (newest to oldest), then bare python3
for cmd in python3.13 python3.12 python3.11 python3.10 python3; do
  PY=$(command -v "$cmd" 2>/dev/null) && \
  "$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null && \
  break || PY=""
done
```

If `$PY` is empty, **stop and tell the user** they need Python 3.10+ installed. Do NOT fall back to an older Python — it will fail at `pip install`.

**Create venv and install:**

```bash
cd <destination>
$PY -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
```

**Verify** the memory MCP server loads:

```bash
cd <destination>
PYTHONPATH=src .venv/bin/python3 -c "import memory_mcp; print('Memory MCP OK')"
```

If venv/pip/verify fails, report the error but don't abort — the project is still usable without the memory MCP.

### 8. Print summary

After all steps complete, print:

```
Project created at: <destination>

⚠️  IMPORTANT: Exit this Claude Code session now.
    The init process changes the working directory, which can break
    the shell sandbox for the rest of the session.

Next steps:
  1. Exit this session (type /exit or Ctrl+C)
  2. cd <destination>
  3. Run: claude
  4. Edit BRIEF.md with your project description
  5. Say: "Read BRIEF.md and help me plan the implementation."

Template version: <TEMPLATE_VERSION>
Sync baseline: .claude/template-ref/ (bootstrapped)
```

## Error Handling

- If rsync fails, try falling back to manual `cp -r` with exclusions
- If git init fails (e.g., git not installed), warn but continue
- If venv/pip fails, warn but continue — pre-flight hook will catch it later
- Never leave a partially-created project without telling the user what happened
