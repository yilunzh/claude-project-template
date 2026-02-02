# Analyze Project for Template Improvements

Review this project's workflow configuration and identify improvements that should become part of the default templates.

## Analysis Scope

Compare against templates at:
- Claude: `~/side_project/claude-project-template`
- Cursor: `~/side_project/cursor-project-template`

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

Provide:
1. **Recommended improvements** - Changes worth adding to templates, with rationale
2. **Project-specific** - Things that work here but shouldn't be in templates
3. **Template issues** - Things in templates that should be removed/changed based on experience

Then ask which improvements to apply.
