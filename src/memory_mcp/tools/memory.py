"""Agent memory tools.

Captures behavioral learnings (corrections, preferences, patterns) to
.claude/memory/ and retrieves them for context injection. Part of the
self-improving agent system.

Memory files are personal (gitignored) and can be promoted to commands/agents
through the learning review -> approval -> apply_proposal pipeline.
"""

import logging
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import yaml

from ._git_helpers import get_current_branch, run_git
from ._paths import (
    get_memory_corrections_dir,
    get_memory_dir,
    get_memory_patterns_dir,
    get_memory_preferences_dir,
    get_memory_reflections_dir,
    get_project_root,
)
from ._registry import register_tool

logger = logging.getLogger("memory-mcp")

# --- Schema constants ---

VALID_MEMORY_TYPES = {"correction", "preference", "pattern"}
VALID_SCOPES = {"universal", "domain", "investigation", "one_time"}
VALID_STATUSES = {
    "active",
    "pattern_candidate",
    "promoted",
    "decayed",
    "rejected",
    "superseded",
}
VALID_PHASES = {
    "discovery",
    "pre_flight",
    "analysis",
    "smell_test",
    "validation",
    "all",
}
VALID_SIGNALS = {
    "explicit_correction",
    "explicit_preference",
    "observed_pattern",
    "session_extraction",
}
EXCLUDED_STATUSES = {"decayed", "promoted", "rejected", "superseded"}

# Scoring weights
WEIGHT_TABLE = 5
WEIGHT_DOMAIN = 3
WEIGHT_PHASE = 2
WEIGHT_REINFORCEMENT = 2
WEIGHT_RECENCY = 1
GATEKEEPER_THRESHOLD = 2.0


# --- Utilities ---


def _slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    slug = text.lower()
    slug = re.sub(r"[.\s/\\]+", "-", slug)
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:60]


def _type_to_dir(memory_type: str) -> Path:
    """Map a memory type to its storage directory."""
    dirs = {
        "correction": get_memory_corrections_dir(),
        "preference": get_memory_preferences_dir(),
        "pattern": get_memory_patterns_dir(),
    }
    return dirs[memory_type]


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (chars / 4)."""
    return max(1, len(text) // 4)


def _recency_score(last_seen_str: str) -> float:
    """Calculate recency score from last_seen date string.

    Returns 1.0 for today, decaying to 0.1 for 90+ days old.
    """
    try:
        last_seen = datetime.strptime(last_seen_str, "%Y-%m-%d").date()
        days_ago = (date.today() - last_seen).days
    except (ValueError, TypeError):
        return 0.1

    if days_ago <= 0:
        return 1.0
    elif days_ago <= 7:
        return 0.7 + 0.3 * (1 - days_ago / 7)
    elif days_ago <= 30:
        return 0.3 + 0.4 * (1 - (days_ago - 7) / 23)
    elif days_ago <= 90:
        return 0.1 + 0.2 * (1 - (days_ago - 30) / 60)
    else:
        return 0.1


def _reinforcement_score(times_reinforced: int) -> float:
    """Normalize reinforcement count to 0-1 range."""
    return min(times_reinforced / 5.0, 1.0)


def validate_memory_entry(entry: dict) -> Optional[str]:
    """Validate a memory entry dict.

    Returns an error message string if invalid, or None if valid.
    """
    # Required fields
    for field in ("id", "type", "summary", "scope", "status"):
        if field not in entry or not entry[field]:
            return f"Missing required field: '{field}'"

    if entry["type"] not in VALID_MEMORY_TYPES:
        return (
            f"Invalid type '{entry['type']}'. "
            f"Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}"
        )

    if entry["scope"] not in VALID_SCOPES:
        return (
            f"Invalid scope '{entry['scope']}'. "
            f"Must be one of: {', '.join(sorted(VALID_SCOPES))}"
        )

    if entry["status"] not in VALID_STATUSES:
        return (
            f"Invalid status '{entry['status']}'. "
            f"Must be one of: {', '.join(sorted(VALID_STATUSES))}"
        )

    return None


def _atomic_write_yaml(path: Path, data: dict) -> None:
    """Write YAML atomically using temp file + rename.

    Prevents corruption from concurrent writes by writing to a
    temporary file first, then atomically replacing the target.
    """
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# --- Tools ---


@register_tool(
    name="capture_memory",
    description=(
        "Capture a behavioral learning (correction, preference, or pattern) "
        "to the agent memory system. Called when the user corrects the agent, "
        "states a preference, or a workflow pattern is observed."
    ),
    parameters={
        "type": {
            "type": "string",
            "description": "Memory type: correction, preference, or pattern",
        },
        "summary": {
            "type": "string",
            "description": "One-line summary of the learning",
        },
        "detail": {
            "type": "string",
            "description": "Detailed explanation (optional)",
        },
        "domain": {
            "type": "string",
            "description": "Data domain this applies to (optional, null = all)",
        },
        "tables": {
            "type": "string",
            "description": "Comma-separated table names this applies to (optional)",
        },
        "phase": {
            "type": "string",
            "description": (
                "Investigation phase: discovery, pre_flight, analysis, "
                "smell_test, validation, all"
            ),
        },
        "scope": {
            "type": "string",
            "description": "Scope: universal, domain, investigation, one_time",
        },
        "signal": {
            "type": "string",
            "description": (
                "How captured: explicit_correction, explicit_preference, "
                "observed_pattern, session_extraction"
            ),
        },
        "investigation": {
            "type": "string",
            "description": "Current investigation slug (optional)",
        },
    },
    required=["type", "summary", "scope"],
)
def capture_memory(
    type: str,
    summary: str,
    scope: str,
    detail: str = "",
    domain: str = "",
    tables: str = "",
    phase: str = "all",
    signal: str = "explicit_correction",
    investigation: str = "",
) -> str:
    """Capture a behavioral learning to the memory store.

    Writes a YAML file to .claude/memory/<type>s/<slug>.yaml.

    Args:
        type: Memory type (correction, preference, pattern).
        summary: One-line summary.
        scope: Scope (universal, domain, investigation, one_time).
        detail: Optional detailed explanation.
        domain: Optional data domain.
        tables: Optional comma-separated table names.
        phase: Investigation phase (default "all").
        signal: How this was captured.
        investigation: Current investigation slug.

    Returns:
        Confirmation message or error string.
    """
    # Validate type
    if type not in VALID_MEMORY_TYPES:
        return (
            f"Error: Invalid type '{type}'. "
            f"Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}"
        )

    # Validate scope
    if scope not in VALID_SCOPES:
        return (
            f"Error: Invalid scope '{scope}'. "
            f"Must be one of: {', '.join(sorted(VALID_SCOPES))}"
        )

    # Validate phase
    if phase and phase not in VALID_PHASES:
        return (
            f"Error: Invalid phase '{phase}'. "
            f"Must be one of: {', '.join(sorted(VALID_PHASES))}"
        )

    # Validate signal
    if signal and signal not in VALID_SIGNALS:
        return (
            f"Error: Invalid signal '{signal}'. "
            f"Must be one of: {', '.join(sorted(VALID_SIGNALS))}"
        )

    # Parse tables from comma-separated string
    tables_list = (
        [t.strip() for t in tables.split(",") if t.strip()] if tables else []
    )

    # --- Deduplication check ---
    dup_path, dup_entry, match_type = _find_duplicate(type, tables_list, summary)

    if match_type == "duplicate" and dup_entry:
        # Reinforce existing memory instead of creating new
        dup_id = dup_entry.get("id", "unknown")
        result = reinforce_memory(dup_id, session=investigation)
        return f"Reinforced existing memory: {result}"

    if match_type == "contradiction" and dup_path and dup_entry:
        # Supersede old memory, create new one
        old_id = dup_entry.get("id", "unknown")
        slug = _slugify(summary)
        new_id = f"{type}-{slug}"
        dup_entry["status"] = "superseded"
        dup_entry["superseded_by"] = new_id
        try:
            _atomic_write_yaml(dup_path, dup_entry)
        except Exception as e:
            logger.warning(f"Failed to mark old memory as superseded: {e}")
        # Fall through to create the new entry

    # Generate ID and filename
    slug = _slugify(summary)
    memory_id = f"{type}-{slug}"

    # Determine target directory
    target_dir = _type_to_dir(type)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Find available filename
    filepath = target_dir / f"{slug}.yaml"
    suffix = 2
    while filepath.exists():
        filepath = target_dir / f"{slug}-{suffix}.yaml"
        suffix += 1

    # Path traversal protection
    resolved = filepath.resolve()
    resolved_dir = target_dir.resolve()
    if not resolved.is_relative_to(resolved_dir):
        return "Error: Path traversal detected. Cannot write outside memory directory."

    # Build entry
    today = date.today().isoformat()
    entry = {
        "id": memory_id,
        "type": type,
        "signal": signal or "explicit_correction",
        "summary": summary,
        "detail": detail or None,
        "domain": domain or None,
        "tables": tables_list,
        "phase": phase or "all",
        "scope": scope,
        "times_reinforced": 1,
        "first_seen": today,
        "last_seen": today,
        "source_sessions": [investigation] if investigation else [],
        "status": "active",
        "promoted_to": None,
        "superseded_by": None,
    }

    # Validate before writing
    error = validate_memory_entry(entry)
    if error:
        return f"Error: {error}"

    # Write YAML
    try:
        _atomic_write_yaml(filepath, entry)

        msg = (
            f"Captured **{type}** to memory: `{summary}` "
            f"(id: {memory_id}, file: {filepath.name})"
        )
        if match_type == "contradiction" and dup_entry:
            old_id = dup_entry.get("id", "unknown")
            msg += f" (superseded previous memory `{old_id}`)"
        return msg
    except Exception as e:
        logger.error(f"Error writing memory entry: {e}")
        return f"Error writing memory entry: {str(e)}"


@register_tool(
    name="load_relevant_memories",
    description=(
        "Load memories relevant to the current context. Called at session "
        "start, table encounter, or phase transition to inject behavioral "
        "context from past sessions."
    ),
    parameters={
        "domain": {
            "type": "string",
            "description": "Current investigation domain (optional)",
        },
        "tables": {
            "type": "string",
            "description": "Comma-separated table names being worked with (optional)",
        },
        "phase": {
            "type": "string",
            "description": "Current investigation phase (optional)",
        },
        "max_tokens": {
            "type": "string",
            "description": "Token budget for memory injection (default: 1000)",
        },
    },
)
def load_relevant_memories(
    domain: str = "",
    tables: str = "",
    phase: str = "",
    max_tokens: str = "1000",
) -> str:
    """Load and score memories relevant to the current context.

    Scans all YAML files in .claude/memory/ subdirectories, scores each
    against the provided context, and returns the top entries formatted
    as compact markdown within the token budget.

    Args:
        domain: Current investigation domain.
        tables: Comma-separated table names.
        phase: Current investigation phase.
        max_tokens: Token budget (default 1000).

    Returns:
        Formatted markdown block of relevant memories, or a message
        indicating no relevant memories were found.
    """
    try:
        token_budget = int(max_tokens)
    except (ValueError, TypeError):
        token_budget = 1000

    # Parse tables
    query_tables = set(
        t.strip().lower() for t in tables.split(",") if t.strip()
    ) if tables else set()
    query_domain = domain.strip().lower() if domain else ""
    query_phase = phase.strip().lower() if phase else ""

    # Scan memory directories
    memory_dir = get_memory_dir()
    if not memory_dir.exists():
        return "No relevant memories. (Memory directory does not exist yet.)"

    scan_dirs = [
        get_memory_corrections_dir(),
        get_memory_preferences_dir(),
        get_memory_patterns_dir(),
    ]

    scored_entries = []

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for yaml_file in scan_dir.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    entry = yaml.safe_load(f)
                if not isinstance(entry, dict):
                    continue
            except Exception as e:
                logger.warning(f"Skipping malformed memory file {yaml_file}: {e}")
                continue

            # Filter by status
            status = entry.get("status", "active")
            if status in EXCLUDED_STATUSES:
                continue

            # Score the entry
            score = _score_entry(entry, query_domain, query_tables, query_phase)

            # Gatekeeper threshold
            if score < GATEKEEPER_THRESHOLD:
                continue

            scored_entries.append((score, entry))

    if not scored_entries:
        return "No relevant memories."

    # Sort by score descending
    scored_entries.sort(key=lambda x: x[0], reverse=True)

    # Format within token budget
    return _format_memories(scored_entries, token_budget)


def _score_entry(
    entry: dict,
    query_domain: str,
    query_tables: set[str],
    query_phase: str,
) -> float:
    """Score a memory entry against the current context."""
    score = 0.0

    # Table match (highest weight)
    entry_tables = set(
        t.lower() for t in entry.get("tables", []) if isinstance(t, str)
    )
    if query_tables and entry_tables and query_tables & entry_tables:
        score += WEIGHT_TABLE

    # Domain match
    entry_domain = (entry.get("domain") or "").lower()
    if query_domain and entry_domain and query_domain == entry_domain:
        score += WEIGHT_DOMAIN

    # Phase match
    entry_phase = (entry.get("phase") or "all").lower()
    if query_phase and (entry_phase == query_phase or entry_phase == "all"):
        score += WEIGHT_PHASE

    # Reinforcement score
    times_reinforced = entry.get("times_reinforced", 1)
    if isinstance(times_reinforced, (int, float)):
        score += WEIGHT_REINFORCEMENT * _reinforcement_score(int(times_reinforced))

    # Recency score
    last_seen = entry.get("last_seen", "")
    if isinstance(last_seen, str) and last_seen:
        score += WEIGHT_RECENCY * _recency_score(last_seen)
    elif isinstance(last_seen, date):
        score += WEIGHT_RECENCY * _recency_score(last_seen.isoformat())

    return score


def _format_memories(
    scored_entries: list[tuple[float, dict]], token_budget: int
) -> str:
    """Format scored memory entries as compact markdown within token budget."""
    corrections = []
    preferences = []
    patterns = []

    tokens_used = 0
    header = "## Active Memories\n\n"
    tokens_used += _estimate_tokens(header)

    for score, entry in scored_entries:
        memory_type = entry.get("type", "correction")
        summary = entry.get("summary", "")
        memory_id = entry.get("id", "unknown")
        reinforced = entry.get("times_reinforced", 1)

        # Confidence label
        if reinforced >= 3:
            confidence = "HIGH"
        elif reinforced >= 2:
            confidence = "MED"
        else:
            confidence = "LOW"

        line = f"- **[{confidence}, {reinforced}x]** {summary} `[{memory_id}]`\n"
        line_tokens = _estimate_tokens(line)

        if tokens_used + line_tokens > token_budget:
            break

        tokens_used += line_tokens

        if memory_type == "correction":
            corrections.append(line)
        elif memory_type == "preference":
            preferences.append(line)
        else:
            patterns.append(line)

    # Build output
    parts = [header]

    if corrections:
        parts.append("### Corrections\n")
        parts.extend(corrections)
        parts.append("\n")

    if preferences:
        parts.append("### Preferences\n")
        parts.extend(preferences)
        parts.append("\n")

    if patterns:
        parts.append("### Workflow Notes\n")
        parts.extend(patterns)
        parts.append("\n")

    return "".join(parts).strip()


# --- Helpers for reinforcement and deduplication ---


def _find_memory_by_id(memory_id: str) -> tuple[Optional[Path], Optional[dict]]:
    """Find a memory file by its ID across all subdirectories.

    Returns (filepath, entry_dict) or (None, None) if not found.
    """
    scan_dirs = [
        get_memory_corrections_dir(),
        get_memory_preferences_dir(),
        get_memory_patterns_dir(),
    ]

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for yaml_file in scan_dir.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    entry = yaml.safe_load(f)
                if isinstance(entry, dict) and entry.get("id") == memory_id:
                    return yaml_file, entry
            except Exception:
                continue

    return None, None


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text for dedup matching."""
    # Lowercase, split on non-alphanumeric, filter short words
    words = re.findall(r"[a-z0-9_]+", text.lower())
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "and",
        "but", "or", "not", "no", "if", "then", "than", "that",
        "this", "it", "its", "when", "where", "which", "what",
    }
    return {w for w in words if len(w) > 2 and w not in stop_words}


NEGATION_PAIRS = [
    ({"always"}, {"never"}),
    ({"filter"}, {"dont", "don"}),  # "don't filter" -> "dont" or "don"
    ({"include"}, {"exclude"}),
    ({"left"}, {"inner"}),  # join types
    ({"use"}, {"avoid"}),
]


def _has_contradiction(summary_a: str, summary_b: str) -> bool:
    """Heuristic check for contradicting summaries."""
    words_a = _extract_keywords(summary_a)
    words_b = _extract_keywords(summary_b)

    for pos_set, neg_set in NEGATION_PAIRS:
        a_has_pos = bool(words_a & pos_set)
        a_has_neg = bool(words_a & neg_set)
        b_has_pos = bool(words_b & pos_set)
        b_has_neg = bool(words_b & neg_set)

        if (a_has_pos and b_has_neg) or (a_has_neg and b_has_pos):
            return True

    return False


def _find_duplicate(
    memory_type: str, tables_list: list[str], summary: str
) -> tuple[Optional[Path], Optional[dict], str]:
    """Check for an existing memory that matches this new capture.

    Returns (filepath, entry, match_type) where match_type is one of:
    - "duplicate": same memory, should reinforce
    - "contradiction": conflicting memory, should supersede
    - "none": no match found
    """
    target_dir = _type_to_dir(memory_type)
    if not target_dir.exists():
        return None, None, "none"

    new_tables = set(t.lower() for t in tables_list)
    new_keywords = _extract_keywords(summary)

    if not new_keywords:
        return None, None, "none"

    for yaml_file in target_dir.glob("*.yaml"):
        try:
            with open(yaml_file) as f:
                entry = yaml.safe_load(f)
            if not isinstance(entry, dict):
                continue
        except Exception:
            continue

        # Skip non-active entries
        if entry.get("status") not in ("active", "pattern_candidate"):
            continue

        existing_tables = set(
            t.lower() for t in entry.get("tables", []) if isinstance(t, str)
        )
        existing_keywords = _extract_keywords(entry.get("summary", ""))

        # Check table overlap (if both have tables, they must overlap)
        tables_match = True
        if new_tables and existing_tables:
            tables_match = bool(new_tables & existing_tables)
        elif new_tables or existing_tables:
            # One has tables, the other doesn't -- not a match
            tables_match = False

        if not tables_match:
            continue

        # Check keyword overlap
        if not existing_keywords:
            continue

        overlap = new_keywords & existing_keywords
        overlap_ratio = len(overlap) / min(len(new_keywords), len(existing_keywords))

        if overlap_ratio > 0.5:
            # Check for contradiction
            if _has_contradiction(summary, entry.get("summary", "")):
                return yaml_file, entry, "contradiction"
            return yaml_file, entry, "duplicate"

    return None, None, "none"


# --- Phase 2 Tools ---


@register_tool(
    name="reinforce_memory",
    description=(
        "Reinforce an existing memory when the same correction recurs. "
        "Increments the reinforcement count and may trigger pattern detection."
    ),
    parameters={
        "memory_id": {
            "type": "string",
            "description": "ID of the memory to reinforce",
        },
        "session": {
            "type": "string",
            "description": "Current investigation slug (optional)",
        },
    },
    required=["memory_id"],
)
def reinforce_memory(memory_id: str, session: str = "") -> str:
    """Reinforce an existing memory when the same correction recurs.

    Args:
        memory_id: ID of the memory to reinforce.
        session: Current investigation slug.

    Returns:
        Confirmation with new reinforcement count, or error.
    """
    filepath, entry = _find_memory_by_id(memory_id)

    if filepath is None or entry is None:
        return f"Error: Memory '{memory_id}' not found."

    # Increment reinforcement
    entry["times_reinforced"] = entry.get("times_reinforced", 1) + 1
    entry["last_seen"] = date.today().isoformat()

    # Add session if provided and not already present
    if session:
        sessions = entry.get("source_sessions", [])
        if not isinstance(sessions, list):
            sessions = []
        if session not in sessions:
            sessions.append(session)
        entry["source_sessions"] = sessions

    # Check pattern threshold
    pattern_triggered = False
    if entry["times_reinforced"] >= 3 and entry.get("status") == "active":
        entry["status"] = "pattern_candidate"
        pattern_triggered = True

    # Write back
    try:
        _atomic_write_yaml(filepath, entry)

        count = entry["times_reinforced"]
        msg = f"Reinforced memory `{memory_id}` ({count}x)."
        if pattern_triggered:
            msg += " **Pattern detected** -- this memory is now a candidate for rule promotion."
        return msg

    except Exception as e:
        logger.error(f"Error reinforcing memory: {e}")
        return f"Error reinforcing memory: {str(e)}"


@register_tool(
    name="learning_review",
    description=(
        "Generate an end-of-session learning summary with proposals for "
        "rule/skill changes. Call this at session end to review what the "
        "agent learned and surface any promotion candidates."
    ),
    parameters={
        "investigation": {
            "type": "string",
            "description": "Current investigation slug (optional)",
        },
    },
)
def learning_review(investigation: str = "") -> str:
    """Generate end-of-session learning summary with proposals.

    Args:
        investigation: Current investigation slug.

    Returns:
        Formatted markdown learning review.
    """
    today = date.today().isoformat()

    # Scan all memory files
    scan_dirs = [
        get_memory_corrections_dir(),
        get_memory_preferences_dir(),
        get_memory_patterns_dir(),
    ]

    todays_memories = []
    pattern_candidates = []
    promoted_memories = []
    active_memories = []

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for yaml_file in scan_dir.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    entry = yaml.safe_load(f)
                if not isinstance(entry, dict):
                    continue
            except Exception:
                continue

            last_seen = entry.get("last_seen", "")
            if isinstance(last_seen, date):
                last_seen = last_seen.isoformat()

            if last_seen == today:
                todays_memories.append(entry)

            status = entry.get("status", "")
            if status == "pattern_candidate":
                pattern_candidates.append(entry)
            elif status == "promoted":
                promoted_memories.append(entry)
            elif status == "active":
                active_memories.append(entry)

    # Detect rollback candidates: active memories that contradict promoted ones
    rollback_candidates = []
    for active in active_memories:
        active_tables = set(
            t.lower() for t in active.get("tables", []) if isinstance(t, str)
        )
        active_summary = active.get("summary", "")
        for promoted in promoted_memories:
            promoted_tables = set(
                t.lower() for t in promoted.get("tables", []) if isinstance(t, str)
            )
            if active_tables and promoted_tables and active_tables & promoted_tables:
                if _has_contradiction(active_summary, promoted.get("summary", "")):
                    rollback_candidates.append((promoted, active))

    if not todays_memories and not pattern_candidates and not rollback_candidates:
        return "No learnings to review this session."

    parts = ["# Session Learning Review\n\n"]

    # Section 1: Today's memories
    if todays_memories:
        parts.append(f"## New Memories ({len(todays_memories)})\n\n")
        for mem in todays_memories:
            mem_type = mem.get("type", "correction")
            summary = mem.get("summary", "")
            mem_id = mem.get("id", "unknown")
            reinforced = mem.get("times_reinforced", 1)
            parts.append(
                f"- [{mem_type.upper()}] {summary} "
                f"(`{mem_id}`, {reinforced}x)\n"
            )
        parts.append("\n")

    # Section 2: Pattern candidates
    if pattern_candidates:
        parts.append(f"## Pattern Candidates ({len(pattern_candidates)})\n\n")
        for mem in pattern_candidates:
            summary = mem.get("summary", "")
            mem_id = mem.get("id", "unknown")
            reinforced = mem.get("times_reinforced", 0)
            sessions = mem.get("source_sessions", [])
            parts.append(
                f"- `{mem_id}` -- {summary} "
                f"({reinforced}x, from {len(sessions)} sessions)\n"
            )
        parts.append("\n")

        # Section 3: Proposals
        parts.append("## Proposals\n\n")
        for i, mem in enumerate(pattern_candidates, 1):
            summary = mem.get("summary", "")
            detail = mem.get("detail") or summary
            mem_id = mem.get("id", "unknown")
            reinforced = mem.get("times_reinforced", 0)
            sessions = mem.get("source_sessions", [])
            mem_type = mem.get("type", "correction")
            scope = mem.get("scope", "universal")

            # Suggest scope
            scope_label = "platform" if scope in ("universal", "platform") else "personal"

            parts.append(f"### Proposal {i}: {summary}\n\n")
            parts.append(
                "**Suggested target:** *(agent judgment -- choose the "
                "most appropriate command or agent file)*\n\n"
            )
            parts.append(f"**Proposed addition:**\n> {detail}\n\n")
            parts.append(f"**Evidence:** {reinforced}x reinforced across {len(sessions)} sessions")
            if sessions:
                parts.append(f" ({', '.join(sessions[:5])})")
            parts.append(f"\n**Scope:** {scope_label}\n\n")
            parts.append("**Action:** `[Accept / Reject / Edit / Defer]`\n\n---\n\n")

    # Section 4: Rollback candidates
    if rollback_candidates:
        parts.append(f"## Rollback Candidates ({len(rollback_candidates)})\n\n")
        for promoted, contradicting in rollback_candidates:
            p_id = promoted.get("id", "unknown")
            p_summary = promoted.get("summary", "")
            p_target = promoted.get("promoted_to", "unknown file")
            c_id = contradicting.get("id", "unknown")
            c_summary = contradicting.get("summary", "")

            parts.append(f"### Rollback: {p_summary}\n\n")
            parts.append(
                f"Memory `{p_id}` was promoted to `{p_target}`, "
                f"but a newer correction contradicts it:\n\n"
            )
            parts.append(f"> **New:** {c_summary} (`{c_id}`)\n\n")
            parts.append(f"> **Old (promoted):** {p_summary} (`{p_id}`)\n\n")
            parts.append("**Action:** `[Revert / Keep / Defer]`\n\n---\n\n")

    # Section 5: Memory Usage prompt (agent fills in when presenting)
    parts.append("## Memory Usage\n\n")
    parts.append(
        "*Which loaded memories influenced your behavior this session? "
        "List them below to help improve relevance scoring.*\n\n"
    )
    parts.append("- *(agent: list memories used vs. unused here)*\n")

    return "".join(parts).strip()


@register_tool(
    name="capture_reflection",
    description=(
        "Write a structured session reflection (retro) to memory. "
        "Called at session end to capture what went well and what could improve."
    ),
    parameters={
        "investigation": {
            "type": "string",
            "description": "Current investigation slug",
        },
        "domain": {
            "type": "string",
            "description": "Data domain (optional)",
        },
        "went_well": {
            "type": "string",
            "description": "Comma-separated list of things that went well",
        },
        "could_improve": {
            "type": "string",
            "description": "Comma-separated list of things that could improve",
        },
        "proposed_learning": {
            "type": "string",
            "description": "Key takeaway or proposed behavioral change (optional)",
        },
    },
    required=["investigation", "went_well", "could_improve"],
)
def capture_reflection(
    investigation: str,
    went_well: str,
    could_improve: str,
    domain: str = "",
    proposed_learning: str = "",
) -> str:
    """Write a structured session reflection to memory.

    Args:
        investigation: Investigation slug.
        went_well: Comma-separated list of positives.
        could_improve: Comma-separated list of improvements.
        domain: Optional data domain.
        proposed_learning: Optional key takeaway.

    Returns:
        Confirmation with file path.
    """
    reflections_dir = get_memory_reflections_dir()
    reflections_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(investigation)
    today = date.today().isoformat()
    filename = f"{today}_{slug}.md"
    filepath = reflections_dir / filename

    # Handle collision
    suffix = 2
    while filepath.exists():
        filepath = reflections_dir / f"{today}_{slug}-{suffix}.md"
        suffix += 1

    # Path validation
    resolved = filepath.resolve()
    resolved_dir = reflections_dir.resolve()
    if not resolved.is_relative_to(resolved_dir):
        return "Error: Path traversal detected. Cannot write outside reflections directory."

    # Parse comma-separated lists
    well_items = [item.strip() for item in went_well.split(",") if item.strip()]
    improve_items = [
        item.strip() for item in could_improve.split(",") if item.strip()
    ]

    # Build markdown
    lines = [
        f"# Session Reflection: {investigation}",
        f"Date: {today}",
        f"Investigation: {investigation}",
    ]
    if domain:
        lines.append(f"Domain: {domain}")
    lines.append("")
    lines.append("## What Went Well")
    for item in well_items:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## What Could Improve")
    for item in improve_items:
        lines.append(f"- {item}")

    if proposed_learning:
        lines.append("")
        lines.append("## Proposed Learning")
        lines.append(proposed_learning)

    lines.append("")

    try:
        filepath.write_text("\n".join(lines))
        return f"Captured reflection for `{investigation}` ({filepath.name})"
    except Exception as e:
        logger.error(f"Error writing reflection: {e}")
        return f"Error writing reflection: {str(e)}"


# --- Phase 3: Hard Path Tools ---

# Allowed directories for apply_proposal writes
ALLOWED_WRITE_PREFIXES = [
    ".claude/commands/",
    ".claude/agents/",
]


def _validate_target_path(target_file: str) -> Optional[str]:
    """Validate that the target file is in an allowed directory.

    Returns error message or None if valid.
    """
    normalized = target_file.replace("\\", "/")
    if normalized.startswith("/"):
        return f"Error: Target file must be a relative path, got '{target_file}'"

    for prefix in ALLOWED_WRITE_PREFIXES:
        if normalized.startswith(prefix):
            return None

    return (
        f"Error: Target file '{target_file}' is outside allowed directories. "
        f"Allowed: {', '.join(ALLOWED_WRITE_PREFIXES)}"
    )


def _apply_change_to_file(
    filepath: Path, action: str, content: str, memory_id: str, reinforced: int
) -> tuple[bool, str]:
    """Apply a change to a target file with provenance comment.

    Returns (success, message).
    """
    today = date.today().isoformat()
    provenance = (
        f"\n\n<!-- Memory-promoted: {today}, source: {memory_id}, "
        f"evidence: {reinforced}x reinforced -->\n"
    )

    if action == "append":
        try:
            existing = filepath.read_text()
            new_content = existing.rstrip() + "\n\n" + content + provenance
            filepath.write_text(new_content)
            return True, f"Appended to `{filepath.name}`"
        except Exception as e:
            return False, f"Error writing file: {e}"

    elif action == "remove":
        # Remove content between provenance markers for rollback
        try:
            existing = filepath.read_text()
            # Find the provenance comment for this memory_id
            marker = f"source: {memory_id}"
            if marker not in existing:
                return (
                    False,
                    f"Could not find provenance marker for "
                    f"`{memory_id}` in `{filepath.name}`",
                )

            # Find the promoted content block: everything from the content
            # to the provenance comment (inclusive)
            lines = existing.split("\n")
            new_lines = []
            content_lines = [
                ln.strip() for ln in content.strip().split("\n") if ln.strip()
            ]
            found = False

            i = 0
            while i < len(lines):
                line = lines[i]
                # Check if this line matches the start of the promoted content
                if (
                    not found
                    and content_lines
                    and line.strip() == content_lines[0]
                ):
                    # Look ahead to see if the full content block + provenance is here
                    block_end = i
                    for j in range(i, min(i + len(content_lines) + 10, len(lines))):
                        if marker in lines[j]:
                            block_end = j
                            found = True
                            break

                    if found:
                        # Skip blank lines before the content too
                        while new_lines and new_lines[-1].strip() == "":
                            new_lines.pop()
                        i = block_end + 1
                        # Add revert provenance
                        revert_comment = (
                            f"\n<!-- Reverted: {today}, "
                            f"source: {memory_id} -->\n"
                        )
                        new_lines.append(revert_comment)
                        continue

                new_lines.append(line)
                i += 1

            if not found:
                return False, f"Could not locate promoted content block for `{memory_id}`"

            filepath.write_text("\n".join(new_lines))
            return True, f"Removed promoted content from `{filepath.name}`"

        except Exception as e:
            return False, f"Error during rollback: {e}"

    else:
        return False, f"Unsupported action '{action}'. Use 'append' or 'remove'."


@register_tool(
    name="apply_proposal",
    description=(
        "Apply an approved proposal by editing a command/agent file (personal scope) "
        "or creating a git branch with the change (platform scope). "
        "Call this after the user approves a proposal during learning review."
    ),
    parameters={
        "memory_id": {
            "type": "string",
            "description": "ID of the pattern_candidate memory being promoted",
        },
        "target_file": {
            "type": "string",
            "description": (
                "Relative path to the file to modify "
                "(e.g., '.claude/commands/analysis-principles.md')"
            ),
        },
        "action": {
            "type": "string",
            "description": "What to do: append (add to end), remove (rollback promoted content)",
        },
        "content": {
            "type": "string",
            "description": (
                "Exact content to add (for append) or content "
                "to find and remove (for remove/rollback)"
            ),
        },
        "scope": {
            "type": "string",
            "description": "Scope: personal (edit file directly) or platform (create branch + PR)",
        },
    },
    required=["memory_id", "target_file", "action", "content", "scope"],
)
def apply_proposal(
    memory_id: str,
    target_file: str,
    action: str,
    content: str,
    scope: str,
) -> str:
    """Apply an approved proposal to a command/agent file.

    Args:
        memory_id: ID of the memory being promoted.
        target_file: Relative path to the target file.
        action: 'append' to add content, 'remove' for rollback.
        content: Content to add or locate for removal.
        scope: 'personal' for direct edit, 'platform' for git branch + commit.

    Returns:
        Confirmation or error message.
    """
    # Validate scope
    if scope not in ("personal", "platform"):
        return f"Error: Invalid scope '{scope}'. Must be 'personal' or 'platform'."

    # Validate action
    if action not in ("append", "remove"):
        return f"Error: Invalid action '{action}'. Must be 'append' or 'remove'."

    # Validate target path
    path_error = _validate_target_path(target_file)
    if path_error:
        return path_error

    # Resolve full path
    project_root = get_project_root()
    full_path = project_root / target_file

    if not full_path.exists():
        return f"Error: Target file '{target_file}' does not exist."

    # Find the memory to get reinforcement count
    filepath, entry = _find_memory_by_id(memory_id)
    reinforced = 0
    if entry:
        reinforced = entry.get("times_reinforced", 0)

    if scope == "personal":
        return _apply_personal(
            memory_id, full_path, target_file, action, content, reinforced, filepath, entry
        )
    else:
        return _apply_platform(
            memory_id, full_path, target_file, action,
            content, reinforced, filepath, entry, project_root,
        )


def _apply_personal(
    memory_id: str,
    full_path: Path,
    target_file: str,
    action: str,
    content: str,
    reinforced: int,
    memory_filepath: Optional[Path],
    memory_entry: Optional[dict],
) -> str:
    """Apply a proposal in personal scope (direct file edit)."""
    success, message = _apply_change_to_file(
        full_path, action, content, memory_id, reinforced
    )

    if not success:
        return message

    # Update memory status
    if memory_filepath and memory_entry:
        if action == "append":
            memory_entry["status"] = "promoted"
            memory_entry["promoted_to"] = target_file
        elif action == "remove":
            memory_entry["status"] = "reverted"

        try:
            _atomic_write_yaml(memory_filepath, memory_entry)
        except Exception as e:
            logger.warning(f"Failed to update memory status: {e}")

    if action == "append":
        return f"Applied proposal: {message}. Memory `{memory_id}` promoted."
    else:
        return f"Rolled back: {message}. Memory `{memory_id}` reverted."


def _apply_platform(
    memory_id: str,
    full_path: Path,
    target_file: str,
    action: str,
    content: str,
    reinforced: int,
    memory_filepath: Optional[Path],
    memory_entry: Optional[dict],
    project_root: Path,
) -> str:
    """Apply a proposal in platform scope (git branch + commit)."""
    # Save current branch
    original_branch = get_current_branch(project_root)

    # Generate branch name
    slug = _slugify(memory_id)
    if action == "remove":
        branch_name = f"memory/revert-{slug}"
    else:
        branch_name = f"memory/add-{slug}"

    # Handle branch name collision
    result = run_git(["branch", "--list", branch_name], project_root, check=False)
    if branch_name in result.stdout:
        branch_name = f"{branch_name}-{date.today().isoformat()}"

    # Create and switch to new branch
    result = run_git(["checkout", "-b", branch_name], project_root, check=False)
    if result.returncode != 0:
        return f"Error: Failed to create branch '{branch_name}': {result.stderr.strip()}"

    try:
        # Apply the change
        success, message = _apply_change_to_file(
            full_path, action, content, memory_id, reinforced
        )

        if not success:
            # Switch back on failure
            run_git(["checkout", original_branch], project_root, check=False)
            run_git(["branch", "-D", branch_name], project_root, check=False)
            return message

        # Stage the changed file
        run_git(["add", target_file], project_root, check=False)

        # Build commit message
        if action == "append":
            commit_msg = (
                f"memory: promote {memory_id} to {target_file}\n\n"
                f"Evidence: {reinforced}x reinforced"
            )
            if memory_entry:
                sessions = memory_entry.get("source_sessions", [])
                if sessions:
                    commit_msg += f"\nSessions: {', '.join(sessions[:5])}"
                commit_msg += f"\nSummary: {memory_entry.get('summary', '')}"
        else:
            commit_msg = (
                f"memory: revert {memory_id} from {target_file}\n\n"
                f"Reason: contradicted by newer correction"
            )

        # Commit
        run_git(["commit", "-m", commit_msg], project_root, check=False)

        # Switch back to original branch
        run_git(["checkout", original_branch], project_root, check=False)

        # Update memory status
        if memory_filepath and memory_entry:
            if action == "append":
                memory_entry["status"] = "promoted"
                memory_entry["promoted_to"] = target_file
            elif action == "remove":
                memory_entry["status"] = "reverted"

            try:
                _atomic_write_yaml(memory_filepath, memory_entry)
            except Exception as e:
                logger.warning(f"Failed to update memory status: {e}")

        return (
            f"Branch `{branch_name}` created with "
            f"{'promotion' if action == 'append' else 'rollback'}. "
            f"{message}. Push and create PR when ready."
        )

    except Exception as e:
        # Ensure we switch back on any error
        run_git(["checkout", original_branch], project_root, check=False)
        return f"Error during platform apply: {e}"


# --- Phase 4: Maintenance & Observability ---

DECAY_DAYS = 60
DELETE_DAYS = 90


def _run_maintenance(all_entries: list[tuple[Path, dict]]) -> dict:
    """Run expiration/cleanup maintenance pass.

    Returns summary dict: {decayed: N, deleted: N, archived: N}
    """
    today = date.today()
    summary = {"decayed": 0, "deleted": 0, "archived": 0}

    for filepath, entry in all_entries:
        status = entry.get("status", "active")

        # Promoted and superseded are archived -- never touched
        if status in ("promoted", "superseded"):
            summary["archived"] += 1
            continue

        # Get last_seen date
        last_seen_str = entry.get("last_seen", "")
        if isinstance(last_seen_str, date):
            last_seen_str = last_seen_str.isoformat()
        try:
            last_seen = datetime.strptime(last_seen_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        # Check file mtime -- if file was manually edited after last_seen, skip expiration
        try:
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime).date()
            if mtime > last_seen:
                continue  # Manually edited, don't expire
        except OSError:
            pass

        days_since = (today - last_seen).days

        # Decay active memories older than 60 days
        if status == "active" and days_since > DECAY_DAYS:
            entry["status"] = "decayed"
            try:
                _atomic_write_yaml(filepath, entry)
                summary["decayed"] += 1
            except Exception as e:
                logger.warning(f"Failed to decay memory {filepath}: {e}")

        # Delete decayed memories older than 90 days
        elif status == "decayed" and days_since > DELETE_DAYS:
            try:
                filepath.unlink()
                summary["deleted"] += 1
            except Exception as e:
                logger.warning(f"Failed to delete memory {filepath}: {e}")

    return summary


@register_tool(
    name="memory_stats",
    description=(
        "Report memory system health metrics and run maintenance (expiration, cleanup). "
        "Call periodically or on demand to check system health."
    ),
    parameters={},
)
def memory_stats() -> str:
    """Report memory system health metrics and run maintenance.

    Scans all memory files, counts by status/type, calculates averages,
    identifies notable entries, and runs expiration/cleanup as a side effect.

    Returns:
        Formatted health report.
    """
    memory_dir = get_memory_dir()
    if not memory_dir.exists():
        return "Memory system is empty. Start capturing learnings to begin."

    scan_dirs = [
        ("correction", get_memory_corrections_dir()),
        ("preference", get_memory_preferences_dir()),
        ("pattern", get_memory_patterns_dir()),
    ]

    # Collect all entries
    all_entries: list[tuple[Path, dict]] = []
    type_counts = {"correction": 0, "preference": 0, "pattern": 0, "reflection": 0}
    status_counts = {s: 0 for s in VALID_STATUSES}

    for mem_type, scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for yaml_file in scan_dir.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    entry = yaml.safe_load(f)
                if not isinstance(entry, dict):
                    continue
                all_entries.append((yaml_file, entry))
                type_counts[mem_type] += 1
                status = entry.get("status", "active")
                if status in status_counts:
                    status_counts[status] += 1
            except Exception:
                continue

    # Count reflections
    reflections_dir = get_memory_reflections_dir()
    if reflections_dir.exists():
        type_counts["reflection"] = len(list(reflections_dir.glob("*.md")))

    total = sum(type_counts.values())
    if total == 0:
        return "Memory system is empty. Start capturing learnings to begin."

    # Calculate averages
    reinforcements = [
        e.get("times_reinforced", 1)
        for _, e in all_entries
        if isinstance(e.get("times_reinforced"), (int, float))
    ]
    avg_reinforcement = sum(reinforcements) / len(reinforcements) if reinforcements else 0

    today = date.today()
    ages = []
    for _, e in all_entries:
        fs = e.get("first_seen", "")
        if isinstance(fs, date):
            fs = fs.isoformat()
        try:
            first_seen = datetime.strptime(fs, "%Y-%m-%d").date()
            ages.append((today - first_seen).days)
        except (ValueError, TypeError):
            pass
    avg_age = sum(ages) / len(ages) if ages else 0

    # Find notable entries
    oldest_active = None
    most_reinforced = None
    most_recent_promoted = None

    for _, e in all_entries:
        if e.get("status") == "active":
            fs = e.get("first_seen", "")
            if isinstance(fs, date):
                fs = fs.isoformat()
            if oldest_active is None or fs < (oldest_active.get("first_seen") or "9999"):
                oldest_active = e

        reinforced = e.get("times_reinforced", 0)
        if most_reinforced is None or reinforced > most_reinforced.get("times_reinforced", 0):
            most_reinforced = e

        if e.get("status") == "promoted":
            ls = e.get("last_seen", "")
            if isinstance(ls, date):
                ls = ls.isoformat()
            if most_recent_promoted is None or ls > (most_recent_promoted.get("last_seen") or ""):
                most_recent_promoted = e

    # Run maintenance
    maintenance = _run_maintenance(all_entries)

    # Build report
    parts = ["# Memory System Health\n\n"]

    parts.append("## Summary\n\n")
    parts.append(f"**Total entries:** {total}\n\n")

    parts.append("| Type | Count |\n|------|-------|\n")
    for t, c in type_counts.items():
        if c > 0:
            parts.append(f"| {t.title()} | {c} |\n")
    parts.append("\n")

    parts.append("| Status | Count |\n|--------|-------|\n")
    for s, c in status_counts.items():
        if c > 0:
            parts.append(f"| {s} | {c} |\n")
    parts.append("\n")

    parts.append("## Averages\n\n")
    parts.append(f"- Reinforcement: {avg_reinforcement:.1f}x avg\n")
    parts.append(f"- Age: {avg_age:.0f} days avg\n\n")

    parts.append("## Notable\n\n")
    if oldest_active:
        oa_id = oldest_active.get('id', '?')
        oa_fs = oldest_active.get('first_seen', '?')
        parts.append(
            f"- **Oldest active:** `{oa_id}` (since {oa_fs})\n"
        )
    if most_reinforced:
        mr_id = most_reinforced.get('id', '?')
        mr_count = most_reinforced.get('times_reinforced', 0)
        parts.append(
            f"- **Most reinforced:** `{mr_id}` ({mr_count}x)\n"
        )
    if most_recent_promoted:
        mrp_id = most_recent_promoted.get('id', '?')
        mrp_to = most_recent_promoted.get('promoted_to', '?')
        parts.append(
            f"- **Recently promoted:** `{mrp_id}` to `{mrp_to}`\n"
        )
    parts.append("\n")

    if any(v > 0 for v in maintenance.values()):
        parts.append("## Maintenance\n\n")
        if maintenance["decayed"] > 0:
            parts.append(f"- Decayed {maintenance['decayed']} memories (>60 days unused)\n")
        if maintenance["deleted"] > 0:
            parts.append(f"- Deleted {maintenance['deleted']} memories (>90 days decayed)\n")
        if maintenance["archived"] > 0:
            parts.append(f"- {maintenance['archived']} archived (promoted/superseded)\n")

    return "".join(parts).strip()
