"""Shared path utilities for the memory MCP tools."""

from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory.

    Resolves by walking up from this file's location:
    tools/_paths.py -> memory_mcp -> src -> project root
    """
    return Path(__file__).resolve().parent.parent.parent.parent


def get_claude_dir() -> Path:
    """Get the .claude directory path."""
    return get_project_root() / ".claude"


# --- Memory system paths ---


def get_memory_dir() -> Path:
    """Get the .claude/memory directory for behavioral learnings."""
    return get_claude_dir() / "memory"


def get_memory_corrections_dir() -> Path:
    """Get the corrections subdirectory."""
    return get_memory_dir() / "corrections"


def get_memory_preferences_dir() -> Path:
    """Get the preferences subdirectory."""
    return get_memory_dir() / "preferences"


def get_memory_patterns_dir() -> Path:
    """Get the patterns subdirectory."""
    return get_memory_dir() / "patterns"


def get_memory_reflections_dir() -> Path:
    """Get the reflections subdirectory."""
    return get_memory_dir() / "reflections"
