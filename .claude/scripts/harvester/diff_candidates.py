#!/usr/bin/env python3
"""Diff project files against template-ref copies and scan memory for promotion candidates.

Compares CLAUDE.md, hooks, commands, agents, and settings against their template-ref
counterparts. Also scans memory YAML files for active/pattern_candidate entries.
Outputs a JSON array of structured candidates to stdout.
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print(
        json.dumps({
            "status": "error",
            "message": "PyYAML is required. Install with: pip install pyyaml",
        }),
        file=sys.stderr,
    )
    sys.exit(1)


# Regex for parsing CLAUDE.md section headers with optional policy markers.
# Matches: ## Section Name <!-- template-managed -->
#          ## Section Name <!-- customizable -->
#          ## Section Name  (no marker)
SECTION_HEADER_RE = re.compile(
    r"^##\s+(.+?)(?:\s*<!--\s*(template-managed|customizable)\s*-->)?$"
)

# File mapping: project-relative paths to scan (relative to project root / template-ref).
FILE_PAIRS: list[tuple[str, str]] = [
    ("CLAUDE.md", "CLAUDE.md"),
    (".claude/settings.json", "settings.json"),
]

# Glob-like directory pairs: (project_dir_relative, template_ref_relative, extension)
DIR_PAIRS: list[tuple[str, str, str]] = [
    (".claude/hooks", "hooks", ".py"),
    (".claude/commands", "commands", ".md"),
    (".claude/agents", "agents", ".md"),
]


def parse_claude_md_sections(content: str) -> dict[str, str]:
    """Parse CLAUDE.md content into a mapping of section_name -> policy.

    Returns a dict like:
        {"Development Workflow": "template-managed", "Project Overview": "customizable"}.
    Sections without an explicit marker get policy "unspecified".
    """
    policies: dict[str, str] = {}
    for line in content.splitlines():
        match = SECTION_HEADER_RE.match(line)
        if match:
            section_name = match.group(1).strip()
            policy = match.group(2) or "unspecified"
            policies[section_name] = policy
    return policies


def identify_changed_sections(diff_lines: list[str], section_policies: dict[str, str]) -> list[str]:
    """Identify which CLAUDE.md sections contain changes based on unified diff output.

    Walks through diff hunks and maps changed line ranges back to section headers
    found in the original/new content.
    """
    changed_sections: set[str] = set()
    current_section: str | None = None

    for line in diff_lines:
        # Track section context from both sides of the diff (lines starting with
        # ' ', '+', or '-' that contain section headers).
        stripped = line
        if stripped.startswith((" ", "+", "-")):
            stripped = stripped[1:]

        match = SECTION_HEADER_RE.match(stripped)
        if match:
            current_section = match.group(1).strip()

        # If the line is an actual change (added or removed), record current section.
        if line.startswith("+") and not line.startswith("+++"):
            if current_section:
                changed_sections.add(current_section)
        elif line.startswith("-") and not line.startswith("---"):
            if current_section:
                changed_sections.add(current_section)

    return sorted(changed_sections)


def build_section_policy_map(
    sections_changed: list[str], section_policies: dict[str, str]
) -> dict[str, str]:
    """Build a policy map for only the sections that changed."""
    return {s: section_policies.get(s, "unspecified") for s in sections_changed}


def diff_file(project_path: Path, template_path: Path, relative_name: str) -> dict | None:
    """Produce a candidate dict for a single file pair.

    Returns None if both files are missing or identical.
    """
    project_exists = project_path.is_file()
    template_exists = template_path.is_file()

    if not project_exists and not template_exists:
        return None

    # File only in project (not in template-ref) -> new_file candidate
    if project_exists and not template_exists:
        return {
            "source": "file",
            "file_path": relative_name,
            "change_type": "new_file",
            "sections_changed": [],
            "diff_content": "",
            "section_policy": {},
        }

    # File only in template-ref (deleted from project) - we skip these for now.
    if not project_exists and template_exists:
        return None

    # Both exist - compare contents
    project_lines = project_path.read_text(encoding="utf-8").splitlines(keepends=True)
    template_lines = template_path.read_text(encoding="utf-8").splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            template_lines,
            project_lines,
            fromfile=f"template-ref/{relative_name}",
            tofile=relative_name,
            lineterm="",
        )
    )

    if not diff_lines:
        return None  # Identical

    diff_content = "\n".join(diff_lines)

    # For CLAUDE.md, parse section-level info
    sections_changed: list[str] = []
    section_policy: dict[str, str] = {}

    if relative_name == "CLAUDE.md":
        # Merge policies from both template and project versions
        project_content = project_path.read_text(encoding="utf-8")
        template_content = template_path.read_text(encoding="utf-8")

        # Policies from template-ref are authoritative, overlay with project policies
        section_policies = parse_claude_md_sections(template_content)
        section_policies.update(parse_claude_md_sections(project_content))

        sections_changed = identify_changed_sections(diff_lines, section_policies)
        section_policy = build_section_policy_map(sections_changed, section_policies)

    return {
        "source": "file",
        "file_path": relative_name,
        "change_type": "modified",
        "sections_changed": sections_changed,
        "diff_content": diff_content,
        "section_policy": section_policy,
    }


def collect_file_candidates(project_dir: Path, template_ref: Path) -> list[dict]:
    """Collect all file-based diff candidates."""
    candidates: list[dict] = []

    # 1. Explicit file pairs
    for proj_rel, tmpl_rel in FILE_PAIRS:
        project_path = project_dir / proj_rel
        template_path = template_ref / tmpl_rel
        candidate = diff_file(project_path, template_path, proj_rel)
        if candidate:
            candidates.append(candidate)

    # 2. Directory-based pairs (hooks, commands, agents)
    for proj_dir_rel, tmpl_dir_rel, ext in DIR_PAIRS:
        proj_subdir = project_dir / proj_dir_rel
        tmpl_subdir = template_ref / tmpl_dir_rel

        # Collect all filenames from both sides
        proj_files: set[str] = set()
        tmpl_files: set[str] = set()

        if proj_subdir.is_dir():
            proj_files = {
                f.name for f in proj_subdir.iterdir()
                if f.is_file() and f.name.endswith(ext)
            }
        if tmpl_subdir.is_dir():
            tmpl_files = {
                f.name for f in tmpl_subdir.iterdir()
                if f.is_file() and f.name.endswith(ext)
            }

        all_files = sorted(proj_files | tmpl_files)
        for filename in all_files:
            project_path = proj_subdir / filename
            template_path = tmpl_subdir / filename
            relative_name = f"{proj_dir_rel}/{filename}"
            candidate = diff_file(project_path, template_path, relative_name)
            if candidate:
                candidates.append(candidate)

    return candidates


def scan_memory_file(yaml_path: Path) -> dict | None:
    """Parse a single memory YAML file and return a candidate if eligible.

    Eligible statuses: active, pattern_candidate.
    Excluded: promoted, decayed, rejected, superseded.
    """
    try:
        content = yaml_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
    except Exception as e:
        print(f"Warning: Failed to parse {yaml_path}: {e}", file=sys.stderr)
        return None

    if not isinstance(data, dict):
        return None

    status = data.get("status", "")
    if status not in ("active", "pattern_candidate"):
        return None

    return {
        "source": "memory",
        "memory_id": data.get("id", yaml_path.stem),
        "type": data.get("type", "unknown"),
        "summary": data.get("summary", ""),
        "detail": data.get("detail", ""),
        "scope": data.get("scope", "unknown"),
        "times_reinforced": data.get("times_reinforced", 0),
        "source_sessions": data.get("source_sessions", []),
    }


def collect_memory_candidates(project_dir: Path) -> list[dict]:
    """Scan .claude/memory/ subdirectories for eligible YAML files."""
    candidates: list[dict] = []
    memory_dir = project_dir / ".claude" / "memory"

    if not memory_dir.is_dir():
        return candidates

    subdirs = ["corrections", "preferences", "patterns"]
    for subdir_name in subdirs:
        subdir = memory_dir / subdir_name
        if not subdir.is_dir():
            continue
        for yaml_path in sorted(subdir.glob("*.yaml")):
            candidate = scan_memory_file(yaml_path)
            if candidate:
                candidates.append(candidate)

    return candidates


def main() -> int:
    """Entry point. Parse args, collect candidates, print JSON to stdout."""
    parser = argparse.ArgumentParser(
        description=(
            "Diff project files against template-ref "
            "and scan memory for promotion candidates."
        )
    )
    parser.add_argument(
        "--project-dir",
        required=True,
        help="Path to the project root directory.",
    )
    parser.add_argument(
        "--template-ref",
        required=True,
        help="Path to the template-ref directory.",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    template_ref = Path(args.template_ref).resolve()

    if not project_dir.is_dir():
        print(
            json.dumps({
                "status": "error",
                "message": f"Project directory not found: {project_dir}",
            }),
            file=sys.stderr,
        )
        return 1

    if not template_ref.is_dir():
        print(
            json.dumps({
                "status": "error",
                "message": (
                    "Template-ref not found. "
                    "Run /sync-templates --reverse first."
                ),
            }),
            file=sys.stderr,
        )
        return 1

    candidates: list[dict] = []

    # File diffs
    candidates.extend(collect_file_candidates(project_dir, template_ref))

    # Memory scanning
    candidates.extend(collect_memory_candidates(project_dir))

    print(json.dumps(candidates, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
