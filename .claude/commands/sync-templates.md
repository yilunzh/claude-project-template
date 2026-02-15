# Sync Template Improvements

Analyze a project's workflow configuration against the templates, or pull template improvements to a project.

## Usage

```
/sync-templates <project> [--reverse]
/sync-templates --reverse <project>
```

**Arguments (flexible order):**
- `<project>` - Required. Local path (`~/projects/foo`) or GitHub repo (`github.com/user/repo`)
- `--reverse` - Optional. Pull improvements FROM templates TO the project

**Examples:**
- `/sync-templates ~/side_project/household_tracker` - Analyze project for template improvements
- `/sync-templates --reverse ~/side_project/household_tracker` - Pull template improvements to project
- `/sync-templates github.com/user/repo` - Analyze a GitHub repo

## Template Locations

Auto-detected from this command's location:
- **Claude template**: The repository containing this command file
- **Cursor template**: Sibling directory `../cursor-project-template`

## Process

### Default Mode: Project → Templates

Analyze a project to find improvements worth adding to the templates.

1. **Inventory both sides**
   - **Template**: Recursively list ALL files under `.claude/`, `docs/`, and root config files (CLAUDE.md, BRIEF.md, etc.) in the template repo
   - **Project**: Same recursive listing for the target project (local path: use Glob; GitHub repo: use `gh api` to list trees recursively)
   - Compare file lists to identify files that exist in one side but not the other

2. **Fetch and compare contents**
   - For files present in both: diff contents to find meaningful differences
   - For files only in the project: evaluate as potential template additions
   - For files only in the template: note as already covered (no action needed)
   - **IMPORTANT**: Read the corresponding template files BEFORE claiming something is a "potential addition" — it may already exist in the template under the same or similar path

3. **Evaluate each difference**
   - Is it generalizable to most projects?
   - Did it actually improve the workflow?
   - Is it adding necessary or unnecessary complexity?

4. **Present recommendations**
   - Recommend changes worth adding to templates
   - Skip project-specific customizations
   - Ask which to apply

### Reverse Mode: Templates → Project

Pull the latest template improvements into a project.

1. **Inventory both sides**
   - **Template**: Recursively list ALL files under `.claude/`, `docs/`, and root config files (CLAUDE.md, BRIEF.md, etc.) in the template repo
   - **Project**: Same recursive listing for the target project (local path: use Glob; GitHub repo: use `gh api` to list trees recursively)
   - Compare file lists to identify files that exist in one side but not the other

2. **Fetch and compare contents**
   - For files present in both: diff contents to find meaningful differences
   - For files only in the template: evaluate as candidates to add to the project
   - For files only in the project: note as project-specific (no action needed)

3. **Evaluate relevance**
   - Which template features would benefit this project?
   - Are there project-specific reasons to skip certain features?

4. **Present recommendations**
   - Show what would be added/updated
   - Ask which to apply to the project

## What to Analyze

1. **CLAUDE.md / Workflow Rules**
   - New workflow patterns that proved useful
   - Refined instructions that reduced errors
   - Better escalation/autonomous decision boundaries

2. **Settings & Permissions** (`.claude/settings.json`)
   - `allowedCommands` - Commands that should be auto-allowed in templates
   - `permissions` - Permission patterns worth defaulting
   - MCP server configurations that are broadly useful

3. **Hooks**
   - New hooks that enforce useful behaviors
   - Improved hook logic (better detection, clearer messages)
   - Hooks that should be removed or simplified

4. **Commands & Agents**
   - New commands that are broadly applicable
   - Agent improvements that generalize

5. **Process Documentation**
   - Ideation workflow refinements
   - Testing/verification patterns

## Evaluation Criteria

For each difference found, assess:
- **Generalizability**: Does this apply to most projects, or just this one?
- **Value**: Did this actually improve the workflow?
- **Simplicity**: Is this adding necessary complexity or unnecessary overhead?

## Output

### Default Mode (Project → Templates)
1. **Recommended improvements** - Changes worth adding to templates, with rationale
2. **Project-specific** - Things that work here but shouldn't be in templates
3. **Template issues** - Things in templates that should be removed/changed

### Reverse Mode (Templates → Project)
1. **Recommended additions** - Template features to add to the project
2. **Already present** - Template features the project has (possibly customized)
3. **Skip** - Template features not relevant to this project

Then ask which changes to apply.
