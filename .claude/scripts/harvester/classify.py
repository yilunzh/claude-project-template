#!/usr/bin/env python3
"""Classify harvest candidates into three tiers using coded rules.

Tier 1 (Auto-Promote): Universal memories with strong reinforcement and no project terms.
Tier 2 (Review): Ambiguous candidates needing agent/human review.
Tier 3 (Auto-Skip): Project-specific or scoped candidates that should not propagate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def load_candidates(path: Path) -> list[dict[str, Any]]:
    """Load candidate list from a JSON file."""
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array in {path}, got {type(data).__name__}")
    return data


def load_terms(path: Path) -> set[str]:
    """Load project-specific terms from a project-terms.yaml file.

    Aggregates terms from all sources (from_brief, from_dirname, from_models, custom).
    Custom entries prefixed with '-' are treated as removals.
    Returns a set of lowercased terms.
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    if not data or "terms" not in data:
        return set()

    terms_section = data["terms"]
    collected: set[str] = set()
    removals: set[str] = set()

    for key in ("from_brief", "from_dirname", "from_models", "custom"):
        entries = terms_section.get(key, []) or []
        for entry in entries:
            entry_str = str(entry).strip()
            if entry_str.startswith("-"):
                removals.add(entry_str.lstrip("-").strip().lower())
            else:
                # Strip leading '+' if present (custom additions)
                cleaned = entry_str.lstrip("+").strip().lower()
                if cleaned:
                    collected.add(cleaned)

    return collected - removals


def _text_contains_any_term(text: str, terms: set[str]) -> str | None:
    """Check if text contains any project-specific term (case-insensitive).

    Returns the first matched term, or None if no match.
    """
    if not text or not terms:
        return None
    text_lower = text.lower()
    for term in sorted(terms):  # sorted for deterministic output
        if term in text_lower:
            return term
    return None


def _candidate_has_project_terms(candidate: dict[str, Any], terms: set[str]) -> str | None:
    """Check candidate fields for project-specific terms.

    Returns the first matched term, or None.
    """
    fields_to_check = ("summary", "detail", "diff_content", "file_path", "sections_changed")
    for field in fields_to_check:
        value = candidate.get(field)
        if value is None:
            continue
        # sections_changed can be a list
        if isinstance(value, list):
            for item in value:
                match = _text_contains_any_term(str(item), terms)
                if match:
                    return match
        else:
            match = _text_contains_any_term(str(value), terms)
            if match:
                return match
    return None


def _all_sections_customizable(candidate: dict[str, Any]) -> bool:
    """Check if all changed sections have policy 'customizable'.

    Only applies to candidates with section_policy data.
    Returns False if no section policy data exists (safe default).
    """
    section_policy = candidate.get("section_policy")
    if not section_policy:
        return False

    # section_policy is a dict mapping section names to their policy
    if isinstance(section_policy, dict):
        policies = list(section_policy.values())
        if not policies:
            return False
        return all(p == "customizable" for p in policies)

    return False


def _is_memory_candidate(candidate: dict[str, Any]) -> bool:
    """Check if candidate originates from a memory entry."""
    return candidate.get("source") == "memory"


def _is_file_candidate(candidate: dict[str, Any]) -> bool:
    """Check if candidate originates from a file diff."""
    return candidate.get("source") == "file"


def _is_new_file(candidate: dict[str, Any]) -> bool:
    """Check if candidate represents a new file (not in template-ref)."""
    return candidate.get("change_type") == "new"


def classify_candidate(candidate: dict[str, Any], terms: set[str]) -> dict[str, Any]:
    """Classify a single candidate into Tier 1, 2, or 3.

    Returns a new dict with the original fields plus tier, tier_reason, and skip_reason.
    """
    result = {**candidate}

    # --- Tier 3 checks (Auto-Skip) ---
    # Any single condition triggers Tier 3.

    # Check 1: Contains project-specific terms
    matched_term = _candidate_has_project_terms(candidate, terms)
    if matched_term:
        result["tier"] = 3
        result["tier_reason"] = f"Contains project-specific term: '{matched_term}'"
        result["skip_reason"] = f"Project term '{matched_term}' found in candidate"
        return result

    # Check 2: Only modifies customizable CLAUDE.md sections
    if _all_sections_customizable(candidate):
        result["tier"] = 3
        result["tier_reason"] = "All changed sections are customizable"
        result["skip_reason"] = "Only modifies customizable CLAUDE.md sections"
        return result

    # Check 3: Memory with non-universal scope
    if _is_memory_candidate(candidate):
        scope = candidate.get("scope", "")
        if scope in ("domain", "investigation", "one_time"):
            result["tier"] = 3
            result["tier_reason"] = f"Memory scope is '{scope}'"
            result["skip_reason"] = f"Memory scope '{scope}' is not promotable"
            return result

    # Check 4: New file referencing project-specific paths/models
    if _is_file_candidate(candidate) and _is_new_file(candidate):
        file_content = candidate.get("file_content", "") or candidate.get("diff_content", "")
        content_term = _text_contains_any_term(str(file_content), terms)
        if content_term:
            result["tier"] = 3
            result["tier_reason"] = f"New file references project-specific term: '{content_term}'"
            result["skip_reason"] = f"New file contains project term '{content_term}'"
            return result

    # --- Tier 1 checks (Auto-Promote) ---
    # ALL conditions must be true.

    if _is_memory_candidate(candidate):
        scope = candidate.get("scope", "")
        times_reinforced = candidate.get("times_reinforced", 0)
        is_universal = scope == "universal"
        is_reinforced = times_reinforced >= 3
        no_project_terms = matched_term is None  # already checked above

        # Check: not referencing a customizable CLAUDE.md section
        not_customizable_ref = not _all_sections_customizable(candidate)

        if is_universal and is_reinforced and no_project_terms and not_customizable_ref:
            result["tier"] = 1
            result["tier_reason"] = (
                f"Universal memory, {times_reinforced}x reinforced, no project terms"
            )
            result["skip_reason"] = None
            return result

    # --- Tier 2 (Review) ---
    # Everything that didn't match Tier 1 or Tier 3.

    result["tier"] = 2
    result["tier_reason"] = _build_tier2_reason(candidate)
    result["skip_reason"] = None
    return result


def _build_tier2_reason(candidate: dict[str, Any]) -> str:
    """Build a descriptive reason for why a candidate landed in Tier 2."""
    parts: list[str] = []

    if _is_memory_candidate(candidate):
        scope = candidate.get("scope", "unknown")
        times_reinforced = candidate.get("times_reinforced", 0)
        parts.append(f"Memory (scope={scope}, {times_reinforced}x reinforced)")
        if scope != "universal":
            parts.append("non-universal scope")
        if times_reinforced < 3:
            parts.append(f"below reinforcement threshold ({times_reinforced} < 3)")
    elif _is_file_candidate(candidate):
        change_type = candidate.get("change_type", "unknown")
        parts.append(f"File diff ({change_type})")
    else:
        parts.append("Unknown source type")

    parts.append("needs review")
    return ", ".join(parts)


def classify_all(
    candidates: list[dict[str, Any]], terms: set[str]
) -> list[dict[str, Any]]:
    """Classify all candidates and return the annotated list."""
    return [classify_candidate(c, terms) for c in candidates]


def main() -> None:
    """Entry point: parse args, load data, classify, output JSON."""
    parser = argparse.ArgumentParser(
        description="Classify harvest candidates into tiers (1=auto-promote, 2=review, 3=auto-skip)"
    )
    parser.add_argument(
        "--candidates",
        required=True,
        help="Path to candidates JSON file (output from diff_candidates.py)",
    )
    parser.add_argument(
        "--terms",
        required=True,
        help="Path to project-terms.yaml (output from extract_terms.py)",
    )
    args = parser.parse_args()

    candidates_path = Path(args.candidates)
    terms_path = Path(args.terms)

    # Validate candidates file
    if not candidates_path.exists():
        print(f"Error: Candidates file not found: {candidates_path}", file=sys.stderr)
        sys.exit(1)

    # Load candidates
    try:
        candidates = load_candidates(candidates_path)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Error loading candidates: {e}", file=sys.stderr)
        sys.exit(1)

    # Handle empty candidates
    if not candidates:
        print(json.dumps([], indent=2))
        sys.exit(0)

    # Load terms (graceful on missing/empty)
    terms: set[str] = set()
    if terms_path.exists():
        try:
            terms = load_terms(terms_path)
        except Exception as e:
            print(f"Warning: Could not load terms from {terms_path}: {e}", file=sys.stderr)
            # Continue with empty terms — nothing will be auto-skipped by terms
    else:
        print(f"Warning: Terms file not found: {terms_path}. Proceeding with no terms.", file=sys.stderr)

    # Classify
    results = classify_all(candidates, terms)

    # Output
    print(json.dumps(results, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
