"""Shared test fixtures for memory MCP tools.

Provides temp memory directories and monkeypatched paths so all tools
operate on isolated test data.
"""


import pytest


@pytest.fixture
def tmp_memory(tmp_path, monkeypatch):
    """Create a temporary memory directory structure for memory tool tests.

    Monkeypatches memory path functions so all tools operate on the temp dir.
    Returns the tmp_path (project root).
    """
    import memory_mcp.tools._paths as paths_mod
    import memory_mcp.tools.memory as memory_mod

    # Create memory subdirectories
    memory_dir = tmp_path / ".claude" / "memory"
    (memory_dir / "corrections").mkdir(parents=True)
    (memory_dir / "preferences").mkdir(parents=True)
    (memory_dir / "patterns").mkdir(parents=True)
    (memory_dir / "reflections").mkdir(parents=True)

    # Monkeypatch all memory path functions
    monkeypatch.setattr(paths_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(paths_mod, "get_claude_dir", lambda: tmp_path / ".claude")
    monkeypatch.setattr(paths_mod, "get_memory_dir", lambda: memory_dir)
    monkeypatch.setattr(
        paths_mod, "get_memory_corrections_dir", lambda: memory_dir / "corrections"
    )
    monkeypatch.setattr(
        paths_mod, "get_memory_preferences_dir", lambda: memory_dir / "preferences"
    )
    monkeypatch.setattr(
        paths_mod, "get_memory_patterns_dir", lambda: memory_dir / "patterns"
    )
    monkeypatch.setattr(
        paths_mod, "get_memory_reflections_dir", lambda: memory_dir / "reflections"
    )

    # Also patch the imports inside memory.py itself
    monkeypatch.setattr(memory_mod, "get_memory_dir", lambda: memory_dir)
    monkeypatch.setattr(
        memory_mod, "get_memory_corrections_dir", lambda: memory_dir / "corrections"
    )
    monkeypatch.setattr(
        memory_mod, "get_memory_preferences_dir", lambda: memory_dir / "preferences"
    )
    monkeypatch.setattr(
        memory_mod, "get_memory_patterns_dir", lambda: memory_dir / "patterns"
    )
    monkeypatch.setattr(
        memory_mod, "get_memory_reflections_dir", lambda: memory_dir / "reflections"
    )

    return tmp_path


@pytest.fixture
def sample_memory_correction():
    """Return kwargs for a valid correction capture."""
    return {
        "type": "correction",
        "summary": "Filter voided transactions before aggregating",
        "scope": "universal",
        "detail": "Voided transactions inflate revenue by ~15%",
        "domain": "billing",
        "tables": "billing_transactions",
        "phase": "analysis",
        "signal": "explicit_correction",
        "investigation": "test-investigation",
    }


@pytest.fixture
def tmp_memory_git(tmp_memory):
    """Extends tmp_memory with an initialized git repo for platform scope tests.

    Returns tmp_path (same as tmp_memory).
    """
    import subprocess

    # Initialize git repo in the tmp_path
    subprocess.run(
        ["git", "init"], cwd=str(tmp_memory), capture_output=True, text=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_memory), capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(tmp_memory), capture_output=True, text=True,
    )

    # Create and commit the commands directory so git has something to work with
    commands_dir = tmp_memory / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    test_command = commands_dir / "test-rule.md"
    test_command.write_text("# Test Rule\n\nExisting content.\n")

    subprocess.run(
        ["git", "add", "."], cwd=str(tmp_memory), capture_output=True, text=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=str(tmp_memory), capture_output=True, text=True,
    )

    return tmp_memory
