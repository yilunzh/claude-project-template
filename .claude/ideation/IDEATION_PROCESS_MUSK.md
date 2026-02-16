# Ideation System Process — Musk 5-Step Enhanced (Track B)

> A structured workflow that transforms a simple idea into a complete execution package through iterative discovery, feedback, and **deliberate subtraction**. This process embeds the Musk 5-Step Engineering Philosophy at every decision point.
>
> **This is Track B** of an A/B test. Track A uses the original `IDEATION_PROCESS.md`. Both processes produce the same artifact structure, but this one applies deletion-first thinking, first-principles reasoning, and schedule-as-constraint at every phase.
>
> **See also:** `IDEATION_PROCESS.md` (Track A / Control)

**Input:** Simple prompt (e.g., "expense tracking for roommates")
**Output:** Complete package ready for implementation — with fewer features than you started with

---

## Core Principles

| Principle | Description |
|-----------|-------------|
| **Reaction-based refinement** | Generate 2-4 options, user reacts (select/comment), converge. Never ask "what do you want?" — show options instead. |
| **Progressive fidelity** | Start loose (concepts), formalize as understanding deepens (specs → prototypes) |
| **Interview mode** | Streamlined interaction — present choices, user selects. Minimize prose, maximize decisions. |
| **Feedback propagation** | Changes in one area trigger review of dependent areas |
| **First-principles reasoning** | Challenge assumptions, explore "why" before "how", document trade-offs. Every requirement must trace to a fundamental need — not precedent, not analogy, not "best practice." |
| **Visual validation** | 80-85% fidelity prototypes required before greenlight |
| **Deletion-first design** | The default action is removal. Every feature, screen, component, and requirement must justify its existence or be deleted. Target 10% deletions — if nothing gets reinstated, you didn't delete enough. |
| **Schedule as design constraint** | If the plan is too long, the design is too complex. >2 sprints → return to Solution Definition, not add resources. Time pressure reveals unnecessary complexity. |

---

## The 5-Step Sequence

Before diving into phases, understand the sequence that governs all decisions in this process. **Order matters — never skip ahead.**

```
Step 1: Question the requirements
  └─► "Is this requirement real? Who needs it? What happens if we don't build it?"
        ↓
Step 2: Delete the part or process
  └─► "Remove it entirely. See what breaks."
        ↓
Step 3: Simplify or optimize
  └─► "Now — and only now — simplify what remains."
        ↓
Step 4: Accelerate cycle time
  └─► "How do we ship the simplified version faster?"
        ↓
Step 5: Automate
  └─► "Only automate what survived steps 1-4."
```

**The critical insight:** Most engineers start at step 3 (optimize) or step 5 (automate). The first two steps — questioning and deleting — are where the real leverage lives.

---

## Mandatory Output Format

All solution proposals within this process use this 7-section format. No exceptions — the format IS the thinking framework.

```
1. First-principles framing — Why does this problem exist? What's the fundamental need?
2. Requirements audit — Owner + rationale for each requirement. Who asked for this and why?
3. Deletions proposed — What we're removing, what breaks, what simplifies, confidence level
4. Simplified design — The design AFTER deletion. Not the original with things crossed out.
5. Acceleration opportunities — How to ship the simplified version faster
6. Automation assessment — What (if anything) should be automated. Justify against steps 1-4.
7. Risks + fastest validating experiments — What could go wrong, and the cheapest way to find out
```

---

## Workflow Phases

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: PROBLEM DISCOVERY                                             │
│  Goal: Understand WHY we're doing this — and whether we should at all  │
│                                                                         │
│  Activities:                                                            │
│  - Identify the pain point                                              │
│  - Understand current state / workarounds                               │
│  - Define target users                                                  │
│  - Explore "why" chains (keep asking why until hitting fundamental)     │
│  - List assumptions (validated vs unvalidated)                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  5-STEP: SUBTRACTION CHECK                                      │    │
│  │  - "What if the solution is removing something that exists?"    │    │
│  │  - "What unnecessary complexity currently surrounds this pain?" │    │
│  │  - "Would users be better served by fewer features, not more?" │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  Output: discovery.md                                                   │
│  Exit criteria: Problem clearly articulated, user confirmed,           │
│                 subtraction opportunity explicitly considered            │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 2: SOLUTION DEFINITION                                           │
│  Goal: Define WHAT we're building — after questioning everything       │
│                                                                         │
│  Activities:                                                            │
│  - Generate 2-4 solution directions                                     │
│  - User reacts, selects direction                                       │
│  - Define scope (in/out)                                                │
│  - Write user stories / requirements                                    │
│  - Define non-functional requirements                                   │
│  - Define success criteria                                              │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  5-STEP REQUIREMENTS AUDIT (mandatory before exit)              │    │
│  │                                                                 │    │
│  │  For EVERY requirement:                                         │    │
│  │  1. Owner — Who specifically asked for this? Name a person or   │    │
│  │     user segment. "Everyone" is not an owner.                   │    │
│  │  2. First-principles rationale — Why does this requirement      │    │
│  │     exist? Trace to a fundamental user need, not precedent      │    │
│  │     or "best practice" or "competitors do it."                  │    │
│  │  3. Deletion test — What breaks if we remove this? If nothing   │    │
│  │     critical breaks, delete it.                                 │    │
│  │                                                                 │    │
│  │  Deletion target: 10% of requirements.                          │    │
│  │  If 0% are deleted, you haven't questioned hard enough.         │    │
│  │  If nothing gets reinstated later, you didn't delete enough.    │    │
│  │                                                                 │    │
│  │  Output: Requirements Audit table + Deletion Log in             │    │
│  │  requirements.md (see templates below)                          │    │
│  │                                                                 │    │
│  │  Apply the mandatory 7-section format to the solution proposal. │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  Output: requirements.md (with audit table + deletion log)             │
│  Exit criteria: Scope locked, requirements audited,                    │
│                 ≥10% deletion target met, deletion log populated       │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: DESIGN DISCOVERY                                              │
│  Goal: Establish design language with an "undesign" bias               │
│                                                                         │
│  Activities:                                                            │
│  - Review existing product design (if any)                              │
│  - Gather references (what user likes/dislikes)                         │
│  - Generate 2-3 visual directions                                       │
│  - User reacts, converge on style                                       │
│  - Document design principles                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  5-STEP: UNDESIGN BIAS                                          │    │
│  │  - Default to removing visual elements, not adding              │    │
│  │  - For each proposed element: "Does the user need this to       │    │
│  │    accomplish their goal, or does it make US feel thorough?"    │    │
│  │  - Fewer UI states > comprehensive state handling               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  Output: design-language.md                                             │
│  Exit criteria: Design direction established, unnecessary elements     │
│                 actively removed                                        │
│  Note: Can skip if design language already exists for project           │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 4: DESIGN SPECIFICATION                                          │
│  Goal: Detail HOW it looks — with the fewest screens possible          │
│                                                                         │
│  Activities:                                                            │
│  - Map user flow end-to-end                                             │
│  - For each screen:                                                     │
│    ┌───────────────────────────────────────────────────────────────┐    │
│    │ FIRST: "Can this screen be eliminated entirely?"              │    │
│    │ THEN:  "Can it be merged with another screen?"                │    │
│    │ ONLY THEN: Specify layout, components, interactions           │    │
│    └───────────────────────────────────────────────────────────────┘    │
│    - Generate 2-3 layout options                                        │
│    - User reacts, select approach                                       │
│    - Specify: layout, components, interactions, copy, states            │
│  - Document edge cases (empty, error, loading, offline)                 │
│  - Generate HTML/CSS prototypes                                         │
│                                                                         │
│  Output: design-specs/, prototypes/                                     │
│  Exit criteria: User approves prototypes, no screen exists without     │
│                 passing the elimination check                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 5: ARCHITECTURE                                                  │
│  Goal: Define HOW it's built — with minimal moving parts               │
│                                                                         │
│  Activities:                                                            │
│  - Identify technical components needed                                 │
│  - Define data models                                                   │
│  - Define API contracts                                                 │
│  - Identify risks and mitigations                                       │
│  - Define CI/quality pipeline                                           │
│  - Define security requirements                                         │
│  - Cross-reference against docs/PATTERNS.md Security Checklist          │
│  - Suggest high-level implementation phases                             │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  5-STEP: ARCHITECTURE DELETION + SIMPLIFICATION                 │    │
│  │                                                                 │    │
│  │  Deletion pass — for every component, API endpoint, and data    │    │
│  │  model: "What breaks if this doesn't exist?"                    │    │
│  │  If nothing critical → delete it.                               │    │
│  │                                                                 │    │
│  │  Simplification pass:                                           │    │
│  │  - Maximum 3 architectural layers. Justify each.                │    │
│  │  - If you have a "utils" or "helpers" module → something is     │    │
│  │    wrong with the design                                        │    │
│  │  - Every abstraction must serve 2+ concrete use cases NOW       │    │
│  │    (not "might need later")                                     │    │
│  │                                                                 │    │
│  │  Schedule check — if the architecture requires >2 sprints       │    │
│  │  to implement, the architecture is too complex. Return to       │    │
│  │  Phase 2 and cut scope.                                         │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  Output: architecture.md                                                │
│  Exit criteria: Technically feasible, ≤3 layers justified,             │
│                 deletion pass documented                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 6: IMPLEMENTATION PLANNING                                       │
│  Goal: Create actionable roadmap — scope-checked                       │
│                                                                         │
│  Activities:                                                            │
│  - Break architecture into Epics (major workstreams)                    │
│  - Break Epics into Stories (implementable units)                       │
│  - Define acceptance criteria for each story                            │
│  - Identify dependencies between stories                                │
│  - Estimate complexity (S/M/L) for prioritization                       │
│  - Define test requirements per story                                   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  5-STEP: SCOPE GATES                                            │    │
│  │                                                                 │    │
│  │  Gate 1: >15 stories → STOP. Run a deletion pass on stories.   │    │
│  │  You're building too much. Which stories can be cut entirely    │    │
│  │  without losing the core value?                                 │    │
│  │                                                                 │    │
│  │  Gate 2: >2 sprints estimated → STOP. Return to Phase 2.       │    │
│  │  The scope is too large. This is a design problem, not a        │    │
│  │  resourcing problem.                                            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  Output: implementation-plan.md                                         │
│  Exit criteria: All stories have clear acceptance criteria,            │
│                 scope gates passed                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 7: HANDOFF                                                       │
│  Goal: Package everything — with A/B comparison data                   │
│                                                                         │
│  Activities:                                                            │
│  - Compile all artifacts                                                │
│  - Write executive summary                                              │
│  - Note what needs human refinement (15-20%)                            │
│  - Define verification criteria                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  5-STEP: COMPARISON METRICS                                     │    │
│  │                                                                 │    │
│  │  Record the following in the handoff for A/B comparison:        │    │
│  │  - Requirements deleted (from Deletion Log)                     │    │
│  │  - Final feature count (user stories)                           │    │
│  │  - Architecture layers                                          │    │
│  │  - Estimated LOC / files                                        │    │
│  │  - Session count                                                │    │
│  │  - Subjective quality rating (user, 1-5)                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  Output: Complete handoff package                                       │
│  Exit criteria: Ready for implementation, metrics recorded              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Research When Stuck

**In any phase, when facing unclear decisions:**

1. **Identify the uncertainty** — What specifically are we unsure about?
2. **Research existing solutions:**
   - How do competitors/similar products handle this?
   - What patterns exist in the industry?
   - What have others tried that failed?
   - Are there relevant design patterns or best practices?
3. **Synthesize findings** — Present options informed by research
4. **Present to user** — "Here's how others solve this: [A, B, C]. Which resonates?"

**5-Step addition:** Before researching "how others do it," first ask: "Should we be doing this at all?" Research should validate need, not just find implementation approaches.

**Research triggers:**
- No clear "right answer" among options
- User says "I'm not sure"
- Novel problem with no obvious precedent
- High-stakes decision with significant trade-offs

**Document findings in artifacts:**
```markdown
## Research: [Topic]
### Question
What were we trying to figure out?

### Findings
| Source | Approach | Pros | Cons |
|--------|----------|------|------|
| Competitor A | ... | ... | ... |
| Competitor B | ... | ... | ... |

### Recommendation
Based on research, we recommend X because...

### Deletion Check
Could we avoid this entirely by removing the feature that requires it?
```

---

## Feedback Loops

Any phase can loop back to previous phases when feedback invalidates earlier decisions:

```
Discovery ↔ Definition ↔ Design ↔ Architecture
    ↑____________|___________|_________|
```

When user provides feedback:
1. Classify: Which phase does this affect?
2. Update: Modify relevant artifact
3. Check dependencies: Does this impact later phases?
4. Propagate: Trigger re-review of affected areas
5. Surface: Ask new questions that emerge
6. **Deletion re-check: Does this feedback create an opportunity to remove something?**

---

## Interaction Model: Interview Mode

**Structure each decision point as:**
```
┌─────────────────────────────────────────────────────────────┐
│  QUESTION: [Clear, specific question]                       │
│                                                             │
│  ○ A) [Option label]                                        │
│       [1-2 sentence description]                            │
│                                                             │
│  ○ B) [Option label]                                        │
│       [1-2 sentence description]                            │
│                                                             │
│  ○ C) [Option label]                                        │
│       [1-2 sentence description]                            │
│                                                             │
│  ○ D) Other: [free text]                                    │
│                                                             │
│  [Optional context that informs the decision]               │
└─────────────────────────────────────────────────────────────┘
```

**5-Step addition:** Always include a "remove/don't build this" option when presenting feature-level decisions. Make deletion a first-class choice, not an afterthought.

**User responds with:**
- Single letter: "B"
- Letter with modification: "B but with X"
- Commentary: "None of these, I want Y"

**System then:**
- Acknowledges decision
- Updates artifacts
- Moves to next decision or presents refined options

---

## Artifact Structure

```
.claude/ideation/<project-slug>/
├── README.md                    # Session status, track designation (A or B)
├── discovery.md                 # Problem space, users, insights
├── requirements.md              # Scope, user stories, AUDIT TABLE, DELETION LOG
├── design-language.md           # Visual/interaction principles
├── decisions.md                 # All decisions with rationale
├── design-specs/
│   ├── screen-1-name.md         # Per-screen specification
│   ├── screen-2-name.md
│   └── ...
├── architecture.md              # Technical approach (≤3 layers)
├── implementation-plan.md       # Epics, stories, acceptance criteria
├── prototypes/
│   ├── index.html               # Entry point
│   ├── screen-1.html
│   ├── screen-2.html
│   └── styles.css
└── handoff/
    ├── SPEC.md                  # Executive summary
    ├── implementation-order.md  # Suggested build sequence
    ├── refinement-notes.md      # What needs human polish
    └── comparison-metrics.md    # A/B test data (Track B only)
```

---

## Artifact Templates

### discovery.md
```markdown
# Discovery: [Project Name]

## Status: DRAFT | COMPLETE
## Last Updated: [timestamp]
## Track: B (Musk 5-Step)

## Problem Statement
[1-2 paragraphs describing the problem]

## Current State
How do users handle this today? What are the pain points?

## Target Users
Who has this problem? How acute is it?

## "Why" Chain
1. Why is this a problem? → [answer]
2. Why does that matter? → [answer]
3. [Continue until fundamental truth]

## Subtraction Check
- What existing complexity surrounds this problem?
- Would removing something (a feature, a step, a rule) solve it without building anything?
- What's the simplest possible intervention?

## Assumptions
| Assumption | Evidence | Confidence | To Validate |
|------------|----------|------------|-------------|
| ... | ... | Low/Med/High | ... |

## Open Questions
- [ ] [Blocking question]
- [ ] [Non-blocking question]
```

### requirements.md
```markdown
# Requirements: [Project Name]

## Status: DRAFT | COMPLETE
## Last Updated: [timestamp]
## Depends On: discovery.md
## Track: B (Musk 5-Step)

## Scope
### In Scope
- [Item 1]
- [Item 2]

### Out of Scope
- [Item 1]
- [Item 2]

## User Stories
### [Category]
- As a [user], I can [action] so that [benefit]
  - Acceptance: [criteria]

## Requirements Audit

| # | Requirement | Owner | First-Principles Rationale | Deletion Test (what breaks?) | Status |
|---|-------------|-------|---------------------------|------------------------------|--------|
| R1 | [requirement] | [name/segment] | [why this exists from first principles] | [what breaks if removed] | Keep / Delete / Reinstated |
| R2 | ... | ... | ... | ... | ... |

**Deletion target: 10%** — Current rate: [X deleted] / [Y total] = [Z]%

## Deletion Log

| # | Deleted Item | Original Justification | Why Deleted | Reinstated? | Reinstatement Reason |
|---|-------------|------------------------|-------------|-------------|---------------------|
| D1 | [what was removed] | [why it was originally included] | [why it was deleted] | Yes/No | [if yes, why] |

## Success Criteria
How will we know this works?
- [Metric 1]
- [Metric 2]

## Constraints
- [Technical constraint]
- [Business constraint]
```

### Screen Spec Template
```markdown
# Screen: [Screen Name]

## Elimination Check
- Can this screen be removed entirely? [Yes/No — rationale]
- Can it be merged with [other screen]? [Yes/No — rationale]

## Purpose
What does this screen accomplish?

## Entry Points
How does user get here?

## Layout
[ASCII mockup or description]

## Components
| Component | Behavior | States |
|-----------|----------|--------|
| ... | ... | ... |

## Interactions
| Trigger | Action | Result |
|---------|--------|--------|
| ... | ... | ... |

## Content/Copy
| Element | Copy |
|---------|------|
| Title | "..." |
| Empty state | "..." |
| Error | "..." |

## Edge Cases
- Loading: [description]
- Empty: [description]
- Error: [description]
- Offline: [description]
```

### implementation-plan.md
```markdown
# Implementation Plan: [Project Name]

## Status: DRAFT | COMPLETE
## Last Updated: [timestamp]
## Depends On: architecture.md
## Track: B (Musk 5-Step)

---

## Scope Gate Check

- Total stories: [N]
  - [ ] ≤15 stories (if >15, run deletion pass before proceeding)
- Estimated duration: [N] sprints
  - [ ] ≤2 sprints (if >2, return to Phase 2 and cut scope)

---

## Epic Overview

| Epic | Description | Stories | Complexity |
|------|-------------|---------|------------|
| E1: [Name] | [Brief description] | X stories | S/M/L |
| E2: [Name] | [Brief description] | X stories | S/M/L |

---

## Epic 1: [Epic Name]

**Goal:** [What this epic accomplishes]
**Dependencies:** [Other epics or external requirements]

### Story 1.1: [Story Title]

**As a** [user type]
**I want** [capability]
**So that** [benefit]

**Acceptance Criteria:**
- [ ] [Specific, testable criterion]
- [ ] [Specific, testable criterion]

**Technical Notes:**
- [Implementation hint or constraint]

**Test Requirements:**
- [ ] Unit: [what to test]
- [ ] Integration: [what to test]

**Complexity:** S / M / L
**Depends On:** [Story IDs or "None"]

---

## Dependency Graph

[Visual representation of story dependencies]

---

## Implementation Order

1. **Phase 1:** [Stories to complete first]
2. **Phase 2:** [Stories that depend on Phase 1]

---

## Definition of Done

A story is complete when:
- [ ] All acceptance criteria pass
- [ ] Unit tests written and passing
- [ ] No new linter warnings
- [ ] Documentation updated (if user-facing)
```

### Handoff — Comparison Metrics (Track B addition)
```markdown
# Comparison Metrics: [Project Name]

## Track: B (Musk 5-Step)

| Metric | Value | Notes |
|--------|-------|-------|
| Requirements deleted | [N] / [total] ([%]) | From Deletion Log |
| Reinstatement rate | [N] / [deleted] ([%]) | Reinstated after analysis |
| Final feature count | [N] user stories | From implementation-plan.md |
| Architecture layers | [N] | Max 3 justified |
| Estimated LOC | [N] | From architecture estimate or git diff |
| Files created | [N] | New files in feature branch |
| Components/abstractions | [N] | From architecture.md |
| Session count | [N] | From README.md |
| Subjective quality | [1-5] | User rating after implementation |
| Time to complete | [N] sessions | Discovery → handoff |
```

---

## Session Persistence

**Cross-session resumption:**
```
User: /ideate --resume bank-import

System: Resuming "bank-import" ideation (Track B — Musk 5-Step)...

Last session: Jan 30, Design Specification phase
Status: 3 of 7 screens specified
Deletion rate: 2/12 requirements (17%)

Key decisions made:
- [Decision 1]
- [Decision 2]

Picking up where we left off...
```

**Context to preserve:**
- All artifact files
- Decision history with rationale
- Current phase and progress
- Open questions
- User preferences/reactions captured
- **Deletion Log state and audit table**

---

## Integration Points

**Entry:**
- `/ideate "concept description"` — Start new session (tell Claude to follow this process)
- `/ideate --resume <project>` — Resume existing
- `/ideate --list` — Show active ideation sessions

**Standalone audit:**
- `/engineering-review` — Run a 5-step audit on any proposal, feature, or codebase area (works with both tracks)

**Exit to Plan Mode:**
- Ideation produces handoff package (with comparison metrics for Track B)
- User approves package
- System: "Ready for implementation. Enter plan mode?"
- Plan mode receives ideation artifacts as input
