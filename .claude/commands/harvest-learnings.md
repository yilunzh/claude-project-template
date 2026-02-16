# Harvest Learnings

First, log this invocation: `.venv/bin/python3 .claude/hooks/_lib/log_command.py "harvest-learnings"`

Scan the current project for improvements worth propagating back to the template. Classifies candidates into auto-promote, review, and auto-skip tiers.

## Usage

```
/harvest-learnings [--show-all]
```

**Flags:**
- `--show-all` - Also display auto-skipped (Tier 3) candidates with skip reasons

## Prerequisites

- `.claude/template-ref/` must exist. If missing, prompt the user to run `/sync-templates --reverse <template-path>` first.
- `.claude/scripts/harvester/` must contain the pipeline scripts (`extract_terms.py`, `diff_candidates.py`, `classify.py`)

## Process

### Step 1: Run the Pipeline

Execute the harvester scripts sequentially via Bash. Use `python3` for all script invocations.

```bash
# 1. Extract project-specific terms
python3 .claude/scripts/harvester/extract_terms.py \
  --project-dir . \
  --output .claude/template-ref/project-terms.yaml

# 2. Generate candidate list (file diffs + memory scan)
python3 .claude/scripts/harvester/diff_candidates.py \
  --project-dir . \
  --template-ref .claude/template-ref \
  > /tmp/harvest-candidates.json

# 3. Classify candidates into tiers
python3 .claude/scripts/harvester/classify.py \
  --candidates /tmp/harvest-candidates.json \
  --terms .claude/template-ref/project-terms.yaml \
  > /tmp/harvest-classified.json
```

If any script fails, report the error and stop.

### Step 2: Load Harvest Queue

Read `.claude/harvest-queue.yaml` if it exists. Merge any deferred items back into the candidate pipeline:
- For each queued item, add it to the classified list for re-evaluation
- Items may have changed tier since they were deferred

### Step 3: Present Results by Tier

Read the classified JSON and present results in three groups:

#### Tier 1: Auto-Promote
List each candidate with:
- Summary/description
- Evidence (times reinforced, sessions)
- Note: "Will auto-create PR on template repo"

#### Tier 2: Review (Agent Reasoning)

For EACH Tier 2 candidate, generate a recommendation:

**Assess on two dimensions:**
1. **Structural signal**: What type of change is this? (error handling improvement, validation pattern, workflow refinement, new tool, documentation improvement)
2. **Semantic signal**: Is this generalizable? (no project-specific terms, similar to existing template patterns, addresses a universal need)

**Present each candidate as:**
```
### [Candidate Name/Summary]
- **Type**: [file diff / memory]
- **Change**: [brief description of what changed]
- **Structural**: [what type of improvement this is]
- **Semantic**: [why it's likely/unlikely to be generalizable]
- **Recommendation**: Promote / Skip
- **Confidence**: High / Medium / Low
```

#### Tier 3: Auto-Skipped
Show count only: "N candidates auto-skipped"
If `--show-all` was passed, also list each with its skip reason.

### Step 4: Get User Decisions

Ask the user:
1. **Tier 1**: "Proceed with auto-PR for these N candidates? [Yes/No/Select]"
   - If "Select", let user pick which ones to promote
2. **Tier 2**: For each candidate, ask "Promote / Skip / Later?"
   - "Later" items are added to `.claude/harvest-queue.yaml`

### Step 5: Execute Promotions

For all candidates marked "Promote" (from both Tier 1 and Tier 2):

1. Read template repo URL from `.claude/template-ref/meta.yaml`
2. Clone the template repo to a temp directory:
   ```bash
   TEMP_DIR=$(mktemp -d)
   gh repo clone <template_repo> "$TEMP_DIR"
   ```
3. Create a branch:
   ```bash
   cd "$TEMP_DIR"
   git checkout -b learning/$(basename $(pwd))-$(date +%Y-%m-%d)
   ```
4. Apply promoted changes:
   - **Memory promotions**: Add the learning as a rule/instruction to the appropriate template file. Use your judgment on where it fits best.
   - **File diffs**: Apply the diff as a patch to the corresponding template file.
   - **Add provenance comments**:
     ```
     <!-- Sourced from: <project-name>, <date> -->
     <!-- Evidence: Nx reinforced, N sessions -->
     ```
5. Commit with a descriptive message listing all promoted changes
6. Push and create PR:
   ```bash
   git push -u origin <branch-name>
   gh pr create --title "learning: harvest from <project-name>" --body "..."
   ```
7. Clean up temp directory
8. Report the PR URL to the user

### Step 6: Update Memory Status

For each promoted memory candidate:
- Update the memory YAML file: set `status: promoted` and `promoted_to: <PR URL>`
- This prevents the memory from appearing in future harvests

For each "Later" candidate:
- Add/update entry in `.claude/harvest-queue.yaml`:
  ```yaml
  items:
    - id: <candidate-id>
      type: <memory/file>
      summary: "<brief description>"
      deferred_at: <today's date>
  ```

Remove items from the queue that were promoted or skipped.

### Step 7: Summary

Present a final summary:
- N candidates promoted (PR: <URL>)
- N candidates skipped
- N candidates deferred to harvest queue
- N candidates auto-skipped (Tier 3)

## Error Handling

- If template-ref doesn't exist: "Template-ref not found. Run `/sync-templates --reverse <template-path>` to bootstrap."
- If no candidates found: "No harvest candidates found. Your project matches the template."
- If `gh` auth fails: "GitHub CLI not authenticated. Run `gh auth login` first."
- If PR creation fails: Report error, but don't lose the candidate list. Suggest manual promotion.
