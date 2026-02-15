#!/usr/bin/env python3
"""Extract project-specific terms from BRIEF.md, directory name, and Python code models.

Part of the learning harvester system. Produces a YAML file with categorized terms
that can be used for project-aware spell checking and code review.

Usage:
    python3 extract_terms.py --project-dir /path/to/project --output /path/to/project-terms.yaml
"""

import argparse
import ast
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# BRIEF.md parsing
# ---------------------------------------------------------------------------

# Common English words to exclude from term extraction
_STOP_WORDS: set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
    "be", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can", "need",
    "it", "its", "this", "that", "these", "those", "i", "we", "you",
    "he", "she", "they", "me", "us", "him", "her", "them", "my", "our",
    "your", "his", "their", "what", "which", "who", "whom", "how", "when",
    "where", "why", "all", "each", "every", "both", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "just", "about", "above", "after",
    "again", "also", "any", "because", "before", "below", "between",
    "during", "if", "into", "out", "over", "then", "there", "through",
    "under", "until", "up", "while", "etc", "e.g", "i.e",
    # Template placeholders from BRIEF.md
    "requirement", "requirements", "add", "another", "describe",
    "project", "building", "built", "build", "use", "using", "used",
    "one", "two", "three", "first", "second", "thing", "things",
    "like", "look", "example", "examples", "link", "site", "app",
    "must", "does", "don", "doesn", "won", "wouldn", "shouldn",
    "see", "read", "fill", "template", "paragraph", "section",
    "optional", "scope", "constraints", "budget", "timeline",
    "hosting", "costs", "platforms", "browsers", "devices",
    "style", "keywords", "modern", "minimal", "playful", "professional",
    "inspiration", "visual", "design", "start", "say", "help", "plan",
    "completing", "brief", "after", "new",
}

# Minimum term length to consider
_MIN_TERM_LENGTH = 3


def extract_terms_from_brief(brief_path: Path) -> list[str]:
    """Extract domain terms from a BRIEF.md file.

    Uses simple heuristics:
    - Capitalized multi-word phrases (product names, proper nouns)
    - Words following "is a", "is an" patterns (definitional phrases)
    - Key nouns from requirement lines
    - Quoted terms
    """
    if not brief_path.exists():
        return []

    text = brief_path.read_text(encoding="utf-8")
    terms: set[str] = set()

    # Strip markdown headers and formatting
    lines = text.splitlines()
    content_lines = [
        line for line in lines
        if not line.startswith("#") and not line.startswith(">") and not line.startswith("---")
    ]
    content = "\n".join(content_lines)

    # 1. Extract capitalized phrases (2+ capitalized words in sequence = likely a name)
    cap_phrases = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", content)
    for phrase in cap_phrases:
        normalized = phrase.lower().strip()
        if normalized and len(normalized) >= _MIN_TERM_LENGTH:
            terms.add(normalized)

    # 2. Extract words after "is a/an" patterns (definitional)
    is_a_patterns = re.findall(
        r"is\s+(?:a|an)\s+([a-zA-Z][a-zA-Z\s-]{2,}?)(?:[.,;!\?\n]|that|which|for|with)",
        content,
        re.IGNORECASE,
    )
    for match in is_a_patterns:
        words = match.strip().lower().split()
        # Take up to 3 words from the definition
        phrase = " ".join(words[:3]).strip()
        if phrase and len(phrase) >= _MIN_TERM_LENGTH:
            terms.add(phrase)

    # 3. Extract standalone capitalized words (potential domain terms)
    cap_words = re.findall(r"\b([A-Z][a-z]{2,})\b", content)
    for word in cap_words:
        lower = word.lower()
        if lower not in _STOP_WORDS and len(lower) >= _MIN_TERM_LENGTH:
            terms.add(lower)

    # 4. Extract quoted terms
    quoted = re.findall(r'"([^"]{2,40})"', content)
    quoted += re.findall(r"'([^']{2,40})'", content)
    for q in quoted:
        cleaned = q.strip().lower()
        if cleaned and len(cleaned) >= _MIN_TERM_LENGTH and not cleaned.startswith("["):
            terms.add(cleaned)

    # 5. Extract hyphenated compound terms
    hyphenated = re.findall(r"\b([a-zA-Z]+-[a-zA-Z]+(?:-[a-zA-Z]+)*)\b", content)
    for h in hyphenated:
        lower = h.lower()
        if lower not in _STOP_WORDS and len(lower) >= _MIN_TERM_LENGTH:
            terms.add(lower)

    # 6. Extract terms from bullet-point requirement lines
    requirement_lines = re.findall(r"^[-*]\s+(.+)$", content, re.MULTILINE)
    for line in requirement_lines:
        # Skip template placeholder lines
        if line.startswith("[") and line.endswith("]"):
            continue
        # Extract notable nouns (words 4+ chars, not stop words)
        words = re.findall(r"\b([a-zA-Z]{4,})\b", line)
        for w in words:
            lower = w.lower()
            if lower not in _STOP_WORDS and len(lower) >= _MIN_TERM_LENGTH:
                terms.add(lower)

    return sorted(terms)


# ---------------------------------------------------------------------------
# Directory name parsing
# ---------------------------------------------------------------------------

def extract_terms_from_dirname(project_dir: Path) -> list[str]:
    """Extract terms by splitting the project directory name on separators."""
    dirname = project_dir.name
    # Split on hyphens, underscores, dots
    parts = re.split(r"[-_.]", dirname)
    terms: set[str] = set()
    for part in parts:
        lower = part.lower().strip()
        if lower and len(lower) >= _MIN_TERM_LENGTH and lower not in _STOP_WORDS:
            terms.add(lower)
    # Also add the full dirname (lowercased) as a term
    full = dirname.lower()
    if len(full) >= _MIN_TERM_LENGTH:
        terms.add(full)
    return sorted(terms)


# ---------------------------------------------------------------------------
# Python AST model extraction
# ---------------------------------------------------------------------------

def _has_decorator(node: ast.ClassDef, name: str) -> bool:
    """Check if a class definition has a specific decorator."""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == name:
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == name:
            return True
    return False


def _inherits_from(node: ast.ClassDef, base_name: str) -> bool:
    """Check if a class inherits from a class matching base_name (simple check)."""
    for base in node.bases:
        # Direct name: class Foo(Model)
        if isinstance(base, ast.Name) and base.id == base_name:
            return True
        # Attribute access: class Foo(models.Model)
        if isinstance(base, ast.Attribute) and base.attr == base_name:
            return True
    return False


def _extract_django_fields(node: ast.ClassDef) -> list[str]:
    """Extract field names from a Django model class."""
    fields: list[str] = []
    for item in ast.walk(node):
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    # Check if assigned value looks like a Django field
                    if isinstance(item.value, ast.Call):
                        func = item.value.func
                        func_name = ""
                        if isinstance(func, ast.Attribute):
                            func_name = func.attr
                        elif isinstance(func, ast.Name):
                            func_name = func.id
                        if "Field" in func_name or "Key" in func_name:
                            fields.append(target.id)
    return fields


def _extract_sqlalchemy_columns(node: ast.ClassDef) -> list[str]:
    """Extract column names from a SQLAlchemy model class."""
    columns: list[str] = []
    for item in ast.walk(node):
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    if isinstance(item.value, ast.Call):
                        func = item.value.func
                        func_name = ""
                        if isinstance(func, ast.Attribute):
                            func_name = func.attr
                        elif isinstance(func, ast.Name):
                            func_name = func.id
                        if func_name in ("Column", "column", "mapped_column"):
                            columns.append(target.id)
    return columns


def _extract_dataclass_fields(node: ast.ClassDef) -> list[str]:
    """Extract field names from a dataclass (annotated assignments)."""
    fields: list[str] = []
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            fields.append(item.target.id)
    return fields


def extract_terms_from_python(project_dir: Path) -> list[str]:
    """Scan Python files for class names and model fields using AST parsing."""
    terms: set[str] = set()

    python_files = list(project_dir.rglob("*.py"))

    # Skip common non-project directories
    skip_dirs = {".venv", "venv", "node_modules", ".git", "__pycache__", ".tox", ".mypy_cache"}

    for py_file in python_files:
        # Skip files in excluded directories
        parts = py_file.relative_to(project_dir).parts
        if any(part in skip_dirs for part in parts):
            continue

        try:
            source = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, ValueError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            # Always add class name
            class_name_lower = _camel_to_terms(node.name)
            terms.update(class_name_lower)

            # Django model
            if _inherits_from(node, "Model"):
                for field in _extract_django_fields(node):
                    terms.add(field.lower())

            # SQLAlchemy model
            if _inherits_from(node, "Base") or _inherits_from(node, "DeclarativeBase"):
                for col in _extract_sqlalchemy_columns(node):
                    terms.add(col.lower())

            # Dataclass
            if _has_decorator(node, "dataclass"):
                for field in _extract_dataclass_fields(node):
                    terms.add(field.lower())

    return sorted(terms)


def _camel_to_terms(name: str) -> list[str]:
    """Split a CamelCase name into lowercase terms.

    Example: 'UserProfile' -> ['userprofile', 'user', 'profile']
    """
    terms = [name.lower()]
    # Split on camelCase boundaries
    parts = re.sub(r"([A-Z])", r" \1", name).split()
    for part in parts:
        lower = part.lower().strip()
        if lower and len(lower) >= _MIN_TERM_LENGTH:
            terms.append(lower)
    return terms


# ---------------------------------------------------------------------------
# Filename-based fallback for non-Python projects
# ---------------------------------------------------------------------------

def extract_terms_from_filenames(project_dir: Path) -> list[str]:
    """Fallback: extract terms from filenames when no Python files found."""
    terms: set[str] = set()
    skip_dirs = {".venv", "venv", "node_modules", ".git", "__pycache__", ".tox"}

    # Look at common source file extensions
    extensions = {"*.ts", "*.tsx", "*.js", "*.jsx", "*.go", "*.rs", "*.java", "*.rb"}
    source_files: list[Path] = []
    for ext in extensions:
        source_files.extend(project_dir.rglob(ext))

    for src_file in source_files:
        parts = src_file.relative_to(project_dir).parts
        if any(part in skip_dirs for part in parts):
            continue

        stem = src_file.stem
        # Split on separators
        name_parts = re.split(r"[-_.]", stem)
        for part in name_parts:
            lower = part.lower()
            if lower and len(lower) >= _MIN_TERM_LENGTH and lower not in _STOP_WORDS:
                terms.add(lower)

    return sorted(terms)


# ---------------------------------------------------------------------------
# Custom term handling (Story 2.2)
# ---------------------------------------------------------------------------

def load_existing_custom_terms(output_path: Path) -> list[str]:
    """Load the custom terms section from an existing output file, if present."""
    if not output_path.exists():
        return []

    try:
        with open(output_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data and isinstance(data, dict):
            terms = data.get("terms", {})
            if isinstance(terms, dict):
                custom = terms.get("custom", [])
                if isinstance(custom, list):
                    return [str(t) for t in custom]
    except (yaml.YAMLError, OSError):
        pass

    return []


def apply_custom_terms(
    auto_terms: set[str],
    custom: list[str],
) -> set[str]:
    """Apply custom term overrides to auto-extracted terms.

    '+term' adds a term, '-term' removes a term from the effective set.
    """
    result = set(auto_terms)
    for entry in custom:
        entry = str(entry).strip()
        if entry.startswith("+"):
            term = entry[1:].strip().lower()
            if term:
                result.add(term)
        elif entry.startswith("-"):
            term = entry[1:].strip().lower()
            result.discard(term)
    return result


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def extract_all_terms(project_dir: Path, output_path: Path) -> dict[str, Any]:
    """Run all extractors and produce the combined terms dictionary."""
    brief_path = project_dir / "BRIEF.md"
    from_brief = extract_terms_from_brief(brief_path)
    from_dirname = extract_terms_from_dirname(project_dir)

    # Try Python AST first; fall back to filename heuristics
    from_models = extract_terms_from_python(project_dir)
    if not from_models:
        from_models = extract_terms_from_filenames(project_dir)

    # Preserve existing custom terms
    custom = load_existing_custom_terms(output_path)

    # Build the output structure
    result: dict[str, Any] = {
        "source_project": project_dir.name,
        "extracted": date.today().isoformat(),
        "terms": {
            "from_brief": sorted(set(from_brief)),
            "from_dirname": sorted(set(from_dirname)),
            "from_models": sorted(set(from_models)),
            "custom": custom,
        },
    }
    return result


def compute_effective_terms(terms_data: dict[str, Any]) -> set[str]:
    """Compute the effective term set after applying custom overrides."""
    terms_section = terms_data.get("terms", {})
    auto_terms: set[str] = set()
    for key in ("from_brief", "from_dirname", "from_models"):
        auto_terms.update(terms_section.get(key, []))

    custom = terms_section.get("custom", [])
    return apply_custom_terms(auto_terms, custom)


def write_output(terms_data: dict[str, Any], output_path: Path) -> None:
    """Write the terms data to a YAML file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(
            terms_data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract project-specific terms for the learning harvester."
    )
    parser.add_argument(
        "--project-dir",
        required=True,
        type=Path,
        help="Path to the project root directory.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Path to write the project-terms YAML file.",
    )
    args = parser.parse_args()

    project_dir: Path = args.project_dir.resolve()
    output_path: Path = args.output.resolve()

    if not project_dir.is_dir():
        error = {"status": "error", "message": f"Project directory not found: {project_dir}"}
        print(json.dumps(error), file=sys.stderr)
        sys.exit(1)

    try:
        terms_data = extract_all_terms(project_dir, output_path)
        write_output(terms_data, output_path)

        effective = compute_effective_terms(terms_data)
        result = {
            "status": "ok",
            "terms_count": len(effective),
            "output": str(output_path),
        }
        print(json.dumps(result))
    except Exception as exc:
        error = {"status": "error", "message": str(exc)}
        print(json.dumps(error), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
