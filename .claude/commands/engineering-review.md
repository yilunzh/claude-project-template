---
description: Run a 5-step engineering audit (question, delete, simplify, accelerate, automate)
---

# 5-Step Engineering Review

First, log this invocation: `.venv/bin/python3 .claude/hooks/_lib/log_command.py "engineering-review"`

Apply the Musk 5-Step Engineering Philosophy to audit a target. This command works regardless of which ideation process was used (Track A or Track B).

## Determine Target

Identify what to audit based on context:

1. **Explicit argument** — If the user specified a feature, proposal, file, or area, audit that
2. **Recent proposal** — If there's a plan, proposal, or feature discussion in the current conversation, audit that
3. **Codebase area** — If neither above applies, ask the user what to audit

## The 5-Step Audit Sequence

**Execute these in order. Order matters — never skip ahead.**

### Step 1: Question the Requirements

For every requirement, feature, or component in the target:
- **Who owns this?** Name a specific person or user segment. "Everyone" is not an owner.
- **First-principles rationale:** Why does this exist? Trace to a fundamental need — not precedent, not "competitors do it," not "best practice."
- **What happens if we don't build/keep this?** Be specific about what actually breaks.

### Step 2: Propose Deletions

Based on Step 1, identify candidates for removal:
- Requirements that lack a clear owner
- Features justified by analogy rather than fundamental need
- Components where nothing critical breaks if removed
- Complexity that exists "just in case"

**Target: 10% deletions.** If you can't find anything to delete, you haven't questioned hard enough.

### Step 3: Simplify What Remains

Only after deletion, simplify:
- Can two components be merged?
- Can a 3-step process become 1 step?
- Are there abstractions serving only one use case? Inline them.
- Is there a simpler architecture that handles the remaining requirements?

### Step 4: Accelerate

How to ship the simplified version faster:
- What's the critical path? Can anything be parallelized?
- Can we ship incrementally instead of all-at-once?
- What can be deferred to a v2 without compromising v1?

### Step 5: Automate (Last!)

Only now, consider automation:
- Is there a manual process that should be automated? Justify why.
- What should explicitly NOT be automated yet? (Most things.)
- Does the automation proposal survive the first 4 steps?

## Output Format

Present findings in this mandatory 7-section format:

### 1. First-Principles Framing

> What is the fundamental problem being solved? Why does it exist? Strip away all assumptions and restate the core need.

### 2. Requirements Audit

| # | Requirement/Feature | Owner | First-Principles Rationale | Deletion Test | Verdict |
|---|---------------------|-------|---------------------------|---------------|---------|
| 1 | [item] | [who] | [why from first principles] | [what breaks if removed] | Keep / Delete / Simplify |

### 3. Proposed Deletions

| # | Item to Delete | What Breaks | What Simplifies | Confidence | Reinstatable? |
|---|----------------|-------------|-----------------|------------|---------------|
| 1 | [item] | [impact] | [benefit] | High/Med/Low | Yes/No |

### 4. Simplified Design

Describe the design AFTER proposed deletions. Not the original with strikethroughs — the clean, simplified version.

### 5. Acceleration Plan

| Opportunity | Impact | Effort | Priority |
|-------------|--------|--------|----------|
| [what] | [time/complexity saved] | [cost] | P1/P2/P3 |

### 6. Automation Assessment

| Candidate | Justify Against Steps 1-4 | Verdict |
|-----------|--------------------------|---------|
| [what] | [why this survived questioning, deletion, and simplification] | Automate / Not Yet / Never |

### 7. Risks + Fastest Validating Experiments

| Risk | Likelihood | Impact | Fastest Experiment |
|------|-----------|--------|-------------------|
| [risk] | High/Med/Low | High/Med/Low | [cheapest way to validate] |

---

### Overall Verdict

**Verdict:** Keep as-is / Simplify / Major rework / Delete entirely

**Deletion Rate:** [X] items proposed for deletion out of [Y] total ([Z]%)
**Reinstatement Expectation:** If 0% gets reinstated after implementation, the deletions weren't aggressive enough.

---

### Key Insight

> [One sentence: the single most important thing this audit revealed]
