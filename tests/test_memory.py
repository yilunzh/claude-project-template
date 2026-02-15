"""Tests for memory.py -- capture, load, scoring, filtering, reinforcement, dedup, review, reflection."""

from datetime import date, timedelta
from pathlib import Path

import yaml

from memory_mcp.tools.memory import (
    capture_memory,
    load_relevant_memories,
    reinforce_memory,
    learning_review,
    capture_reflection,
    apply_proposal,
    memory_stats,
    validate_memory_entry,
)


class TestCaptureMemory:
    def test_capture_correction_all_fields(self, tmp_memory, sample_memory_correction):
        result = capture_memory(**sample_memory_correction)
        assert "Captured **correction**" in result

        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        yaml_files = list(corrections_dir.glob("*.yaml"))
        assert len(yaml_files) == 1

        with open(yaml_files[0]) as f:
            data = yaml.safe_load(f)
        assert data["type"] == "correction"
        assert data["summary"] == "Filter voided transactions before aggregating"
        assert data["scope"] == "universal"
        assert data["domain"] == "billing"
        assert data["tables"] == ["billing_transactions"]
        assert data["phase"] == "analysis"
        assert data["times_reinforced"] == 1
        assert data["status"] == "active"
        assert data["first_seen"] == date.today().isoformat()
        assert data["last_seen"] == date.today().isoformat()
        assert data["source_sessions"] == ["test-investigation"]

    def test_capture_minimal_fields(self, tmp_memory):
        result = capture_memory(
            type="preference",
            summary="Use bullet points for findings",
            scope="universal",
        )
        assert "Captured **preference**" in result

        prefs_dir = tmp_memory / ".claude" / "memory" / "preferences"
        yaml_files = list(prefs_dir.glob("*.yaml"))
        assert len(yaml_files) == 1

        with open(yaml_files[0]) as f:
            data = yaml.safe_load(f)
        assert data["domain"] is None
        assert data["tables"] == []
        assert data["phase"] == "all"
        assert data["times_reinforced"] == 1

    def test_capture_invalid_type(self, tmp_memory):
        result = capture_memory(
            type="invalid_type",
            summary="test",
            scope="universal",
        )
        assert "Invalid type" in result

        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        assert len(list(corrections_dir.glob("*.yaml"))) == 0

    def test_capture_invalid_scope(self, tmp_memory):
        result = capture_memory(
            type="correction",
            summary="test",
            scope="bad_scope",
        )
        assert "Invalid scope" in result

    def test_capture_filename_collision(self, tmp_memory):
        """Two captures with similar slugs but different enough summaries to avoid dedup."""
        result1 = capture_memory(
            type="correction",
            summary="Check column types before aggregating",
            scope="universal",
            domain="billing",
        )
        assert "Captured" in result1

        # Manually create a file with the same slug to force collision
        # (dedup won't trigger because we write the file directly)
        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        slug_file = corrections_dir / "check-column-types-before-aggregating.yaml"
        assert slug_file.exists()

        # Write another file with same slug prefix to test collision path
        # We'll use a different type (preference) to avoid dedup matching
        result2 = capture_memory(
            type="preference",
            summary="Check column types before aggregating",
            scope="universal",
        )
        assert "Captured" in result2

        # Both types should have their own file
        pref_dir = tmp_memory / ".claude" / "memory" / "preferences"
        pref_files = list(pref_dir.glob("*.yaml"))
        assert len(pref_files) == 1

    def test_capture_path_traversal(self, tmp_memory):
        result = capture_memory(
            type="correction",
            summary="../../etc/passwd",
            scope="universal",
        )
        # Slugify strips path separators, so it becomes a safe filename
        # Verify the file is inside the corrections dir
        if "Captured" in result:
            corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
            yaml_files = list(corrections_dir.glob("*.yaml"))
            assert len(yaml_files) == 1
            assert str(yaml_files[0].resolve()).startswith(
                str(corrections_dir.resolve())
            )


class TestLoadRelevantMemories:
    def _create_memory(self, tmp_memory, **overrides):
        """Helper to write a memory YAML file directly."""
        defaults = {
            "id": "correction-test",
            "type": "correction",
            "signal": "explicit_correction",
            "summary": "Test correction",
            "detail": None,
            "domain": "billing",
            "tables": ["billing_transactions"],
            "phase": "analysis",
            "scope": "universal",
            "times_reinforced": 1,
            "first_seen": date.today().isoformat(),
            "last_seen": date.today().isoformat(),
            "source_sessions": [],
            "status": "active",
            "promoted_to": None,
            "superseded_by": None,
        }
        defaults.update(overrides)

        memory_type = defaults["type"]
        type_dir = tmp_memory / ".claude" / "memory" / f"{memory_type}s"
        type_dir.mkdir(parents=True, exist_ok=True)

        slug = defaults["id"].replace(f"{memory_type}-", "")
        filepath = type_dir / f"{slug}.yaml"
        suffix = 2
        while filepath.exists():
            filepath = type_dir / f"{slug}-{suffix}.yaml"
            suffix += 1

        with open(filepath, "w") as f:
            yaml.dump(defaults, f, default_flow_style=False, sort_keys=False)

        return filepath

    def test_load_empty_store(self, tmp_memory):
        result = load_relevant_memories(domain="billing")
        assert "No relevant memories" in result

    def test_load_scoring_table_match(self, tmp_memory):
        # Memory with matching table should score higher
        self._create_memory(
            tmp_memory,
            id="correction-table-match",
            summary="Table match correction",
            tables=["billing_transactions"],
            domain="billing",
        )
        self._create_memory(
            tmp_memory,
            id="correction-domain-only",
            summary="Domain only correction",
            tables=[],
            domain="billing",
        )

        result = load_relevant_memories(
            domain="billing", tables="billing_transactions"
        )
        assert "Active Memories" in result
        # Table match should appear first (higher score)
        table_pos = result.find("Table match correction")
        domain_pos = result.find("Domain only correction")
        assert table_pos < domain_pos

    def test_load_scoring_reinforcement(self, tmp_memory):
        self._create_memory(
            tmp_memory,
            id="correction-low-reinforce",
            summary="Low reinforcement",
            domain="billing",
            times_reinforced=1,
        )
        self._create_memory(
            tmp_memory,
            id="correction-high-reinforce",
            summary="High reinforcement",
            domain="billing",
            times_reinforced=5,
        )

        result = load_relevant_memories(domain="billing")
        high_pos = result.find("High reinforcement")
        low_pos = result.find("Low reinforcement")
        assert high_pos < low_pos

    def test_load_scoring_recency(self, tmp_memory):
        old_date = (date.today() - timedelta(days=60)).isoformat()
        self._create_memory(
            tmp_memory,
            id="correction-old",
            summary="Old correction",
            domain="billing",
            last_seen=old_date,
            first_seen=old_date,
        )
        self._create_memory(
            tmp_memory,
            id="correction-recent",
            summary="Recent correction",
            domain="billing",
            last_seen=date.today().isoformat(),
        )

        result = load_relevant_memories(domain="billing")
        recent_pos = result.find("Recent correction")
        old_pos = result.find("Old correction")
        assert recent_pos < old_pos

    def test_load_status_filtering(self, tmp_memory):
        self._create_memory(
            tmp_memory,
            id="correction-active",
            summary="Active correction",
            domain="billing",
        )
        self._create_memory(
            tmp_memory,
            id="correction-decayed",
            summary="Decayed correction",
            domain="billing",
            status="decayed",
        )
        self._create_memory(
            tmp_memory,
            id="correction-promoted",
            summary="Promoted correction",
            domain="billing",
            status="promoted",
        )

        result = load_relevant_memories(domain="billing")
        assert "Active correction" in result
        assert "Decayed correction" not in result
        assert "Promoted correction" not in result

    def test_load_gatekeeper_threshold(self, tmp_memory):
        # Create a memory with no matching domain/table/phase -- should score below threshold
        self._create_memory(
            tmp_memory,
            id="correction-irrelevant",
            summary="Irrelevant correction",
            domain="fleet-management",
            tables=["vehicle_inventory"],
            phase="validation",
            times_reinforced=1,
        )

        result = load_relevant_memories(domain="billing", tables="billing_transactions")
        assert "Irrelevant correction" not in result

    def test_load_token_budget(self, tmp_memory):
        # Create many memories
        for i in range(30):
            self._create_memory(
                tmp_memory,
                id=f"correction-bulk-{i}",
                summary=f"Bulk correction number {i} with some extra words to take up space",
                domain="billing",
            )

        result = load_relevant_memories(domain="billing", max_tokens="500")
        # Should not contain all 30 -- budget limits output
        count = result.count("Bulk correction number")
        assert count < 30
        assert count > 0

    def test_load_malformed_yaml(self, tmp_memory):
        # Write a malformed file
        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        (corrections_dir / "bad-file.yaml").write_text("{{invalid yaml content")

        # Write a valid memory
        self._create_memory(
            tmp_memory,
            id="correction-good",
            summary="Good correction",
            domain="billing",
        )

        result = load_relevant_memories(domain="billing")
        assert "Good correction" in result  # Valid file still loaded


class TestSchemaValidation:
    def test_schema_validates_required_fields(self):
        # Missing 'type' field
        entry = {
            "id": "test",
            "summary": "test",
            "scope": "universal",
            "status": "active",
        }
        error = validate_memory_entry(entry)
        assert error is not None
        assert "type" in error

    def test_schema_accepts_valid_entry(self):
        entry = {
            "id": "correction-test",
            "type": "correction",
            "summary": "Test correction",
            "scope": "universal",
            "status": "active",
        }
        error = validate_memory_entry(entry)
        assert error is None


class TestDirectoryCreation:
    def test_directories_created_on_first_capture(self, tmp_path, monkeypatch):
        """Capture creates dirs if they don't exist."""
        import memory_mcp.tools._paths as paths_mod
        import memory_mcp.tools.memory as memory_mod

        # Point to a fresh tmp_path WITHOUT pre-created dirs
        memory_dir = tmp_path / ".claude" / "memory"
        monkeypatch.setattr(paths_mod, "get_memory_dir", lambda: memory_dir)
        monkeypatch.setattr(
            paths_mod, "get_memory_corrections_dir", lambda: memory_dir / "corrections"
        )
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

        # No directory exists yet
        assert not memory_dir.exists()

        result = capture_memory(
            type="correction",
            summary="First capture creates dir",
            scope="universal",
        )
        assert "Captured" in result
        assert (memory_dir / "corrections").exists()


# =====================================================================
# Phase 2 Tests: Reinforcement, Dedup, Learning Review, Reflection
# =====================================================================


class TestReinforceMemory:
    def _create_memory(self, tmp_memory, **overrides):
        """Helper to write a memory YAML file directly."""
        defaults = {
            "id": "correction-test",
            "type": "correction",
            "signal": "explicit_correction",
            "summary": "Test correction",
            "detail": None,
            "domain": "billing",
            "tables": ["billing_transactions"],
            "phase": "analysis",
            "scope": "universal",
            "times_reinforced": 1,
            "first_seen": date.today().isoformat(),
            "last_seen": date.today().isoformat(),
            "source_sessions": [],
            "status": "active",
            "promoted_to": None,
            "superseded_by": None,
        }
        defaults.update(overrides)
        memory_type = defaults["type"]
        type_dir = tmp_memory / ".claude" / "memory" / f"{memory_type}s"
        slug = defaults["id"].replace(f"{memory_type}-", "")
        filepath = type_dir / f"{slug}.yaml"
        with open(filepath, "w") as f:
            yaml.dump(defaults, f, default_flow_style=False, sort_keys=False)
        return filepath

    def test_reinforce_increments_count(self, tmp_memory):
        self._create_memory(tmp_memory, id="correction-voided", times_reinforced=1)
        result = reinforce_memory("correction-voided", session="session-2")
        assert "2x" in result
        assert "Pattern detected" not in result

        filepath = tmp_memory / ".claude" / "memory" / "corrections" / "voided.yaml"
        with open(filepath) as f:
            data = yaml.safe_load(f)
        assert data["times_reinforced"] == 2
        assert data["status"] == "active"
        assert "session-2" in data["source_sessions"]

    def test_reinforce_triggers_pattern(self, tmp_memory):
        self._create_memory(tmp_memory, id="correction-voided", times_reinforced=2)
        result = reinforce_memory("correction-voided", session="session-3")
        assert "3x" in result
        assert "Pattern detected" in result

        filepath = tmp_memory / ".claude" / "memory" / "corrections" / "voided.yaml"
        with open(filepath) as f:
            data = yaml.safe_load(f)
        assert data["times_reinforced"] == 3
        assert data["status"] == "pattern_candidate"

    def test_reinforce_already_pattern_candidate(self, tmp_memory):
        self._create_memory(
            tmp_memory,
            id="correction-voided",
            times_reinforced=3,
            status="pattern_candidate",
        )
        result = reinforce_memory("correction-voided")
        assert "4x" in result
        # Should NOT re-trigger "Pattern detected" message
        assert "Pattern detected" not in result

        filepath = tmp_memory / ".claude" / "memory" / "corrections" / "voided.yaml"
        with open(filepath) as f:
            data = yaml.safe_load(f)
        assert data["times_reinforced"] == 4
        assert data["status"] == "pattern_candidate"

    def test_reinforce_not_found(self, tmp_memory):
        result = reinforce_memory("nonexistent-id")
        assert "not found" in result.lower()


class TestDeduplication:
    def test_dedup_same_correction_reinforces(self, tmp_memory):
        # First capture
        result1 = capture_memory(
            type="correction",
            summary="Filter voided transactions before aggregating",
            scope="universal",
            tables="billing_transactions",
        )
        assert "Captured" in result1

        # Same correction again -- should reinforce, not create new
        result2 = capture_memory(
            type="correction",
            summary="Filter voided transactions before aggregating billing",
            scope="universal",
            tables="billing_transactions",
        )
        assert "Reinforced existing" in result2

        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        yaml_files = list(corrections_dir.glob("*.yaml"))
        assert len(yaml_files) == 1  # Only one file, not two

    def test_dedup_different_correction_creates_new(self, tmp_memory):
        capture_memory(
            type="correction",
            summary="Filter voided transactions before aggregating",
            scope="universal",
            tables="billing_transactions",
        )
        result = capture_memory(
            type="correction",
            summary="Check date range completeness before time series",
            scope="universal",
            tables="reservation_dates",
        )
        assert "Captured" in result

        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        yaml_files = list(corrections_dir.glob("*.yaml"))
        assert len(yaml_files) == 2

    def test_dedup_contradiction_supersedes(self, tmp_memory):
        # First: "always filter"
        capture_memory(
            type="correction",
            summary="Always filter status field on billing transactions",
            scope="universal",
            tables="billing_transactions",
        )

        # Contradiction: "never filter"
        result = capture_memory(
            type="correction",
            summary="Never filter status field on billing transactions for audit",
            scope="universal",
            tables="billing_transactions",
        )
        assert "superseded" in result.lower()

        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        yaml_files = list(corrections_dir.glob("*.yaml"))
        assert len(yaml_files) == 2  # Both files exist

        # Check old one is superseded
        for f in yaml_files:
            with open(f) as fh:
                data = yaml.safe_load(fh)
            if "always" in data.get("summary", "").lower():
                assert data["status"] == "superseded"


class TestLearningReview:
    def _create_memory(self, tmp_memory, **overrides):
        """Helper to write a memory YAML file directly."""
        defaults = {
            "id": "correction-test",
            "type": "correction",
            "signal": "explicit_correction",
            "summary": "Test correction",
            "detail": None,
            "domain": "billing",
            "tables": ["billing_transactions"],
            "phase": "analysis",
            "scope": "universal",
            "times_reinforced": 1,
            "first_seen": date.today().isoformat(),
            "last_seen": date.today().isoformat(),
            "source_sessions": [],
            "status": "active",
            "promoted_to": None,
            "superseded_by": None,
        }
        defaults.update(overrides)
        memory_type = defaults["type"]
        type_dir = tmp_memory / ".claude" / "memory" / f"{memory_type}s"
        slug = defaults["id"].replace(f"{memory_type}-", "")
        filepath = type_dir / f"{slug}.yaml"
        suffix = 2
        while filepath.exists():
            filepath = type_dir / f"{slug}-{suffix}.yaml"
            suffix += 1
        with open(filepath, "w") as f:
            yaml.dump(defaults, f, default_flow_style=False, sort_keys=False)
        return filepath

    def test_learning_review_no_activity(self, tmp_memory):
        result = learning_review()
        assert "No learnings to review" in result

    def test_learning_review_new_memories(self, tmp_memory):
        self._create_memory(
            tmp_memory,
            id="correction-today",
            summary="Today's correction",
            last_seen=date.today().isoformat(),
        )
        result = learning_review()
        assert "New Memories" in result
        assert "Today's correction" in result

    def test_learning_review_pattern_candidate(self, tmp_memory):
        self._create_memory(
            tmp_memory,
            id="correction-pattern",
            summary="Recurring pattern correction",
            times_reinforced=3,
            status="pattern_candidate",
            source_sessions=["inv-1", "inv-2", "inv-3"],
        )
        result = learning_review()
        assert "Pattern Candidates" in result
        assert "Proposals" in result
        assert "Recurring pattern correction" in result
        assert "Accept" in result
        assert "3x" in result

    def test_learning_review_mixed(self, tmp_memory):
        # Today's memory (not a pattern)
        self._create_memory(
            tmp_memory,
            id="correction-fresh",
            summary="Fresh correction",
            last_seen=date.today().isoformat(),
        )
        # Pattern candidate from earlier (also seen today)
        self._create_memory(
            tmp_memory,
            id="correction-mature",
            summary="Mature pattern correction",
            times_reinforced=4,
            status="pattern_candidate",
            last_seen=date.today().isoformat(),
            source_sessions=["inv-1", "inv-2", "inv-3", "inv-4"],
        )
        result = learning_review()
        assert "New Memories" in result
        assert "Pattern Candidates" in result
        assert "Fresh correction" in result
        assert "Mature pattern correction" in result


class TestCaptureReflection:
    def test_capture_reflection_all_fields(self, tmp_memory):
        result = capture_reflection(
            investigation="hertz-billing-audit",
            domain="billing",
            went_well="Catalog saved time, Pre-flight caught issues",
            could_improve="Spent too long on joins, Should check catalog first",
            proposed_learning="Always check catalog for joins before schema exploration",
        )
        assert "Captured reflection" in result
        assert "hertz-billing-audit" in result

        reflections_dir = tmp_memory / ".claude" / "memory" / "reflections"
        md_files = list(reflections_dir.glob("*.md"))
        assert len(md_files) == 1

        content = md_files[0].read_text()
        assert "## What Went Well" in content
        assert "Catalog saved time" in content
        assert "## What Could Improve" in content
        assert "Spent too long on joins" in content
        assert "## Proposed Learning" in content
        assert "Always check catalog" in content
        assert "Domain: billing" in content

    def test_capture_reflection_minimal(self, tmp_memory):
        result = capture_reflection(
            investigation="quick-check",
            went_well="Found the answer quickly",
            could_improve="Nothing major",
        )
        assert "Captured reflection" in result

        reflections_dir = tmp_memory / ".claude" / "memory" / "reflections"
        md_files = list(reflections_dir.glob("*.md"))
        assert len(md_files) == 1

        content = md_files[0].read_text()
        assert "## Proposed Learning" not in content

    def test_capture_reflection_filename_collision(self, tmp_memory):
        result1 = capture_reflection(
            investigation="hertz-billing",
            went_well="Good session",
            could_improve="Minor issues",
        )
        assert "Captured reflection" in result1

        result2 = capture_reflection(
            investigation="hertz-billing",
            went_well="Another good session",
            could_improve="Different issues",
        )
        assert "Captured reflection" in result2
        assert "-2" in result2

        reflections_dir = tmp_memory / ".claude" / "memory" / "reflections"
        md_files = list(reflections_dir.glob("*.md"))
        assert len(md_files) == 2

    def test_capture_reflection_path_validation(self, tmp_memory):
        result = capture_reflection(
            investigation="../../etc/passwd",
            went_well="test",
            could_improve="test",
        )
        # Slugify strips path characters, so it becomes safe
        assert "Captured reflection" in result or "Error" in result
        if "Captured reflection" in result:
            reflections_dir = tmp_memory / ".claude" / "memory" / "reflections"
            md_files = list(reflections_dir.glob("*.md"))
            assert len(md_files) == 1
            assert str(md_files[0].resolve()).startswith(
                str(reflections_dir.resolve())
            )


class TestReinforceToProposalPipeline:
    """Integration test: full pipeline from capture through reinforcement to proposal."""

    def test_full_pipeline(self, tmp_memory):
        # Step 1: Capture a correction
        result1 = capture_memory(
            type="correction",
            summary="Filter voided billing transactions before aggregating",
            scope="universal",
            domain="billing",
            tables="billing_transactions",
            investigation="inv-1",
        )
        assert "Captured" in result1

        # Extract the ID from the result
        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        yaml_files = list(corrections_dir.glob("*.yaml"))
        assert len(yaml_files) == 1
        with open(yaml_files[0]) as f:
            data = yaml.safe_load(f)
        memory_id = data["id"]

        # Step 2: Reinforce to 2x
        result2 = reinforce_memory(memory_id, session="inv-2")
        assert "2x" in result2

        # Step 3: Reinforce to 3x -- pattern threshold
        result3 = reinforce_memory(memory_id, session="inv-3")
        assert "3x" in result3
        assert "Pattern detected" in result3

        # Step 4: Learning review should show proposal
        result4 = learning_review(investigation="inv-3")
        assert "Pattern Candidates" in result4
        assert "Proposals" in result4
        assert "Filter voided billing transactions" in result4
        assert "Accept" in result4
        assert "3x" in result4


# =====================================================================
# Phase 3 Tests: Apply Proposal, Rollback
# =====================================================================


class TestApplyProposal:
    def _create_memory(self, tmp_memory, **overrides):
        """Helper to write a memory YAML file directly."""
        defaults = {
            "id": "correction-test",
            "type": "correction",
            "signal": "explicit_correction",
            "summary": "Test correction",
            "detail": None,
            "domain": "billing",
            "tables": ["billing_transactions"],
            "phase": "analysis",
            "scope": "universal",
            "times_reinforced": 3,
            "first_seen": date.today().isoformat(),
            "last_seen": date.today().isoformat(),
            "source_sessions": ["inv-1", "inv-2", "inv-3"],
            "status": "pattern_candidate",
            "promoted_to": None,
            "superseded_by": None,
        }
        defaults.update(overrides)
        memory_type = defaults["type"]
        type_dir = tmp_memory / ".claude" / "memory" / f"{memory_type}s"
        slug = defaults["id"].replace(f"{memory_type}-", "")
        filepath = type_dir / f"{slug}.yaml"
        with open(filepath, "w") as f:
            yaml.dump(defaults, f, default_flow_style=False, sort_keys=False)
        return filepath

    def _create_command_file(self, tmp_memory, name="test-rule.md", content="# Test Rule\n\nExisting content.\n"):
        """Create a command file for testing."""
        commands_dir = tmp_memory / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        filepath = commands_dir / name
        filepath.write_text(content)
        return filepath

    def test_apply_personal_append(self, tmp_memory, monkeypatch):
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        self._create_memory(tmp_memory, id="correction-voided")
        command_file = self._create_command_file(tmp_memory)

        result = apply_proposal(
            memory_id="correction-voided",
            target_file=".claude/commands/test-rule.md",
            action="append",
            content="Filter status fields before aggregating.",
            scope="personal",
        )
        assert "Applied proposal" in result
        assert "promoted" in result.lower()

        # Verify file content
        content = command_file.read_text()
        assert "Filter status fields before aggregating." in content
        assert "Memory-promoted" in content

    def test_apply_personal_provenance(self, tmp_memory, monkeypatch):
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        self._create_memory(tmp_memory, id="correction-voided", times_reinforced=5)
        self._create_command_file(tmp_memory)

        apply_proposal(
            memory_id="correction-voided",
            target_file=".claude/commands/test-rule.md",
            action="append",
            content="New principle.",
            scope="personal",
        )

        content = (tmp_memory / ".claude" / "commands" / "test-rule.md").read_text()
        assert f"source: correction-voided" in content
        assert "5x reinforced" in content
        assert date.today().isoformat() in content

    def test_apply_personal_updates_memory(self, tmp_memory, monkeypatch):
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        mem_file = self._create_memory(tmp_memory, id="correction-voided")
        self._create_command_file(tmp_memory)

        apply_proposal(
            memory_id="correction-voided",
            target_file=".claude/commands/test-rule.md",
            action="append",
            content="New principle.",
            scope="personal",
        )

        with open(mem_file) as f:
            data = yaml.safe_load(f)
        assert data["status"] == "promoted"
        assert data["promoted_to"] == ".claude/commands/test-rule.md"

    def test_apply_path_validation(self, tmp_memory, monkeypatch):
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        result = apply_proposal(
            memory_id="correction-voided",
            target_file="src/memory_mcp/server.py",
            action="append",
            content="malicious content",
            scope="personal",
        )
        assert "Error" in result
        assert "outside allowed" in result

    def test_apply_missing_file(self, tmp_memory, monkeypatch):
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        result = apply_proposal(
            memory_id="correction-voided",
            target_file=".claude/commands/nonexistent.md",
            action="append",
            content="test",
            scope="personal",
        )
        assert "Error" in result
        assert "does not exist" in result

    def test_apply_platform_creates_branch(self, tmp_memory_git, monkeypatch):
        import subprocess
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory_git)

        self._create_memory(tmp_memory_git, id="correction-platform-test")

        result = apply_proposal(
            memory_id="correction-platform-test",
            target_file=".claude/commands/test-rule.md",
            action="append",
            content="Platform promoted principle.",
            scope="platform",
        )
        assert "Branch" in result
        assert "memory/add-" in result

        # Verify branch exists
        branches = subprocess.run(
            ["git", "branch"], cwd=str(tmp_memory_git),
            capture_output=True, text=True,
        )
        assert "memory/add-" in branches.stdout

    def test_apply_platform_commits(self, tmp_memory_git, monkeypatch):
        import subprocess
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory_git)

        self._create_memory(tmp_memory_git, id="correction-commit-test", times_reinforced=4)

        result = apply_proposal(
            memory_id="correction-commit-test",
            target_file=".claude/commands/test-rule.md",
            action="append",
            content="Committed principle.",
            scope="platform",
        )
        assert "Branch" in result

        # Find the branch name and check commit
        branches = subprocess.run(
            ["git", "branch"], cwd=str(tmp_memory_git),
            capture_output=True, text=True,
        )
        branch_name = [b.strip() for b in branches.stdout.strip().split("\n") if "memory/" in b][0]
        log = subprocess.run(
            ["git", "log", branch_name, "--oneline", "-1"],
            cwd=str(tmp_memory_git), capture_output=True, text=True,
        )
        assert "memory: promote" in log.stdout

    def test_apply_platform_returns_to_original(self, tmp_memory_git, monkeypatch):
        import subprocess
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory_git)

        # Get current branch before
        before = subprocess.run(
            ["git", "branch", "--show-current"], cwd=str(tmp_memory_git),
            capture_output=True, text=True,
        ).stdout.strip()

        self._create_memory(tmp_memory_git, id="correction-return-test")

        apply_proposal(
            memory_id="correction-return-test",
            target_file=".claude/commands/test-rule.md",
            action="append",
            content="Return test principle.",
            scope="platform",
        )

        # Verify we're back on original branch
        after = subprocess.run(
            ["git", "branch", "--show-current"], cwd=str(tmp_memory_git),
            capture_output=True, text=True,
        ).stdout.strip()
        assert before == after


class TestApplyProposalValidation:
    """Tests for apply_proposal input validation branches."""

    def test_apply_invalid_scope(self, tmp_memory, monkeypatch):
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        result = apply_proposal(
            memory_id="correction-test",
            target_file=".claude/commands/test.md",
            action="append",
            content="test",
            scope="bad_scope",
        )
        assert "Error" in result
        assert "Invalid scope" in result

    def test_apply_invalid_action(self, tmp_memory, monkeypatch):
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        result = apply_proposal(
            memory_id="correction-test",
            target_file=".claude/commands/test.md",
            action="delete",
            content="test",
            scope="personal",
        )
        assert "Error" in result
        assert "Invalid action" in result

    def test_apply_absolute_path_rejected(self, tmp_memory, monkeypatch):
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        result = apply_proposal(
            memory_id="correction-test",
            target_file="/etc/passwd",
            action="append",
            content="test",
            scope="personal",
        )
        assert "Error" in result
        assert "relative path" in result


class TestRollback:
    def _create_memory(self, tmp_memory, **overrides):
        """Helper to write a memory YAML file directly."""
        defaults = {
            "id": "correction-test",
            "type": "correction",
            "signal": "explicit_correction",
            "summary": "Test correction",
            "detail": None,
            "domain": "billing",
            "tables": ["billing_transactions"],
            "phase": "analysis",
            "scope": "universal",
            "times_reinforced": 1,
            "first_seen": date.today().isoformat(),
            "last_seen": date.today().isoformat(),
            "source_sessions": [],
            "status": "active",
            "promoted_to": None,
            "superseded_by": None,
        }
        defaults.update(overrides)
        memory_type = defaults["type"]
        type_dir = tmp_memory / ".claude" / "memory" / f"{memory_type}s"
        slug = defaults["id"].replace(f"{memory_type}-", "")
        filepath = type_dir / f"{slug}.yaml"
        suffix = 2
        while filepath.exists():
            filepath = type_dir / f"{slug}-{suffix}.yaml"
            suffix += 1
        with open(filepath, "w") as f:
            yaml.dump(defaults, f, default_flow_style=False, sort_keys=False)
        return filepath

    def test_rollback_detection(self, tmp_memory):
        """Active memory contradicting promoted memory shows up in learning review."""
        # Create a promoted memory
        self._create_memory(
            tmp_memory,
            id="correction-always-filter",
            summary="Always filter status field on billing transactions",
            tables=["billing_transactions"],
            status="promoted",
            promoted_to=".claude/commands/analysis-principles.md",
            times_reinforced=3,
        )
        # Create an active memory that contradicts it
        self._create_memory(
            tmp_memory,
            id="correction-never-filter",
            summary="Never filter status field on billing transactions for audit",
            tables=["billing_transactions"],
            status="active",
            last_seen=date.today().isoformat(),
        )

        result = learning_review()
        assert "Rollback" in result
        assert "always-filter" in result or "Always filter" in result
        assert "Revert" in result

    def test_rollback_removes_content(self, tmp_memory, monkeypatch):
        """Remove action strips promoted content from command file."""
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        # Create a command file with promoted content
        commands_dir = tmp_memory / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        command_file = commands_dir / "test-rule.md"
        today = date.today().isoformat()
        command_file.write_text(
            "# Test Rule\n\nExisting content.\n\n"
            "Always filter status fields.\n\n"
            f"<!-- Memory-promoted: {today}, source: correction-rollback-test, evidence: 3x reinforced -->\n"
        )

        # Create the promoted memory
        self._create_memory(
            tmp_memory,
            id="correction-rollback-test",
            summary="Always filter status fields",
            status="promoted",
            promoted_to=".claude/commands/test-rule.md",
            times_reinforced=3,
        )

        result = apply_proposal(
            memory_id="correction-rollback-test",
            target_file=".claude/commands/test-rule.md",
            action="remove",
            content="Always filter status fields.",
            scope="personal",
        )
        assert "Rolled back" in result or "Removed" in result

        # Verify content was removed
        content = command_file.read_text()
        assert "Always filter status fields." not in content
        assert "Existing content." in content
        assert "Reverted" in content

        # Verify memory status updated
        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        for f in corrections_dir.glob("*.yaml"):
            with open(f) as fh:
                data = yaml.safe_load(fh)
            if data.get("id") == "correction-rollback-test":
                assert data["status"] == "reverted"


class TestRollbackEdgeCases:
    """Edge cases for the remove/rollback action in _apply_change_to_file."""

    def _create_memory(self, tmp_memory, **overrides):
        defaults = {
            "id": "correction-test", "type": "correction", "signal": "explicit_correction",
            "summary": "Test", "detail": None, "domain": "billing", "tables": [],
            "phase": "all", "scope": "universal", "times_reinforced": 3,
            "first_seen": date.today().isoformat(), "last_seen": date.today().isoformat(),
            "source_sessions": [], "status": "promoted", "promoted_to": None,
            "superseded_by": None,
        }
        defaults.update(overrides)
        type_dir = tmp_memory / ".claude" / "memory" / f"{defaults['type']}s"
        slug = defaults["id"].replace(f"{defaults['type']}-", "")
        filepath = type_dir / f"{slug}.yaml"
        suffix = 2
        while filepath.exists():
            filepath = type_dir / f"{slug}-{suffix}.yaml"
            suffix += 1
        with open(filepath, "w") as f:
            yaml.dump(defaults, f, default_flow_style=False, sort_keys=False)
        return filepath

    def test_rollback_marker_not_found(self, tmp_memory, monkeypatch):
        """Rollback should fail gracefully if provenance marker is missing."""
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        commands_dir = tmp_memory / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        command_file = commands_dir / "test-rule.md"
        command_file.write_text("# Test Rule\n\nExisting content only.\n")

        self._create_memory(
            tmp_memory, id="correction-no-marker",
            promoted_to=".claude/commands/test-rule.md",
        )

        result = apply_proposal(
            memory_id="correction-no-marker",
            target_file=".claude/commands/test-rule.md",
            action="remove",
            content="Some promoted text.",
            scope="personal",
        )
        assert "Could not find provenance marker" in result

        # File should be unchanged
        assert command_file.read_text() == "# Test Rule\n\nExisting content only.\n"

    def test_rollback_content_not_found(self, tmp_memory, monkeypatch):
        """Rollback should fail if marker exists but content block doesn't match."""
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        commands_dir = tmp_memory / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        command_file = commands_dir / "test-rule.md"
        today = date.today().isoformat()
        # Marker exists but the content we're looking for isn't in the file
        command_file.write_text(
            "# Test Rule\n\nDifferent promoted text.\n\n"
            f"<!-- Memory-promoted: {today}, source: correction-wrong-content, evidence: 3x reinforced -->\n"
        )

        self._create_memory(
            tmp_memory, id="correction-wrong-content",
            promoted_to=".claude/commands/test-rule.md",
        )

        result = apply_proposal(
            memory_id="correction-wrong-content",
            target_file=".claude/commands/test-rule.md",
            action="remove",
            content="This text is NOT in the file.",
            scope="personal",
        )
        assert "Could not locate promoted content block" in result

    def test_rollback_multiline_content(self, tmp_memory, monkeypatch):
        """Rollback should handle multi-line promoted content correctly."""
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        commands_dir = tmp_memory / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        command_file = commands_dir / "test-rule.md"
        today = date.today().isoformat()
        command_file.write_text(
            "# Test Rule\n\nExisting content.\n\n"
            "## Multi-Line Promotion\n\n"
            "Line one of promoted content.\n"
            "Line two of promoted content.\n"
            "Line three of promoted content.\n\n"
            f"<!-- Memory-promoted: {today}, source: correction-multiline, evidence: 3x reinforced -->\n"
        )

        self._create_memory(
            tmp_memory, id="correction-multiline",
            promoted_to=".claude/commands/test-rule.md",
        )

        result = apply_proposal(
            memory_id="correction-multiline",
            target_file=".claude/commands/test-rule.md",
            action="remove",
            content="## Multi-Line Promotion\n\nLine one of promoted content.\nLine two of promoted content.\nLine three of promoted content.",
            scope="personal",
        )
        assert "Rolled back" in result or "Removed" in result

        content = command_file.read_text()
        assert "Line one of promoted content" not in content
        assert "Line two of promoted content" not in content
        assert "Existing content." in content
        assert "Reverted" in content


# =====================================================================
# Phase 4 Tests: Stats, Expiration, Hook, End-to-End
# =====================================================================


class TestMemoryStats:
    def _create_memory(self, tmp_memory, **overrides):
        defaults = {
            "id": "correction-test",
            "type": "correction",
            "signal": "explicit_correction",
            "summary": "Test correction",
            "detail": None,
            "domain": "billing",
            "tables": ["billing_transactions"],
            "phase": "analysis",
            "scope": "universal",
            "times_reinforced": 1,
            "first_seen": date.today().isoformat(),
            "last_seen": date.today().isoformat(),
            "source_sessions": [],
            "status": "active",
            "promoted_to": None,
            "superseded_by": None,
        }
        defaults.update(overrides)
        memory_type = defaults["type"]
        type_dir = tmp_memory / ".claude" / "memory" / f"{memory_type}s"
        slug = defaults["id"].replace(f"{memory_type}-", "")
        filepath = type_dir / f"{slug}.yaml"
        suffix = 2
        while filepath.exists():
            filepath = type_dir / f"{slug}-{suffix}.yaml"
            suffix += 1
        with open(filepath, "w") as f:
            yaml.dump(defaults, f, default_flow_style=False, sort_keys=False)
        return filepath

    def test_stats_counts(self, tmp_memory):
        self._create_memory(tmp_memory, id="correction-a", status="active")
        self._create_memory(tmp_memory, id="correction-b", status="pattern_candidate", times_reinforced=3)
        self._create_memory(tmp_memory, id="preference-c", type="preference", status="active")
        self._create_memory(tmp_memory, id="correction-d", status="promoted", promoted_to="some-rule.md")

        result = memory_stats()
        assert "Memory System Health" in result
        assert "Correction" in result
        assert "Preference" in result
        assert "active" in result
        assert "promoted" in result

    def test_stats_empty(self, tmp_memory):
        # Remove all files to make it empty
        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        for f in corrections_dir.glob("*.yaml"):
            f.unlink()
        result = memory_stats()
        assert "empty" in result.lower()


class TestExpiration:
    def _create_memory(self, tmp_memory, **overrides):
        defaults = {
            "id": "correction-test",
            "type": "correction",
            "signal": "explicit_correction",
            "summary": "Test",
            "detail": None,
            "domain": "billing",
            "tables": [],
            "phase": "all",
            "scope": "universal",
            "times_reinforced": 1,
            "first_seen": date.today().isoformat(),
            "last_seen": date.today().isoformat(),
            "source_sessions": [],
            "status": "active",
            "promoted_to": None,
            "superseded_by": None,
        }
        defaults.update(overrides)
        memory_type = defaults["type"]
        type_dir = tmp_memory / ".claude" / "memory" / f"{memory_type}s"
        slug = defaults["id"].replace(f"{memory_type}-", "")
        filepath = type_dir / f"{slug}.yaml"
        suffix = 2
        while filepath.exists():
            filepath = type_dir / f"{slug}-{suffix}.yaml"
            suffix += 1
        with open(filepath, "w") as f:
            yaml.dump(defaults, f, default_flow_style=False, sort_keys=False)
        # Set mtime to match last_seen so expiration check works
        import os
        ls = defaults.get("last_seen", date.today().isoformat())
        if isinstance(ls, str):
            from datetime import datetime as dt
            ts = dt.strptime(ls, "%Y-%m-%d").timestamp()
            os.utime(filepath, (ts, ts))
        return filepath

    def test_expiration_60day_decay(self, tmp_memory):
        old_date = (date.today() - timedelta(days=65)).isoformat()
        filepath = self._create_memory(
            tmp_memory,
            id="correction-old",
            last_seen=old_date,
            first_seen=old_date,
        )

        memory_stats()  # Triggers maintenance

        with open(filepath) as f:
            data = yaml.safe_load(f)
        assert data["status"] == "decayed"

    def test_expiration_90day_delete(self, tmp_memory):
        old_date = (date.today() - timedelta(days=95)).isoformat()
        filepath = self._create_memory(
            tmp_memory,
            id="correction-ancient",
            last_seen=old_date,
            first_seen=old_date,
            status="decayed",
        )

        assert filepath.exists()
        memory_stats()  # Triggers maintenance
        assert not filepath.exists()

    def test_expiration_promoted_preserved(self, tmp_memory):
        old_date = (date.today() - timedelta(days=120)).isoformat()
        filepath = self._create_memory(
            tmp_memory,
            id="correction-promoted-old",
            last_seen=old_date,
            first_seen=old_date,
            status="promoted",
            promoted_to="some-rule.md",
        )

        memory_stats()  # Triggers maintenance

        # Promoted memory should still exist and be unchanged
        assert filepath.exists()
        with open(filepath) as f:
            data = yaml.safe_load(f)
        assert data["status"] == "promoted"


class TestHook:
    def test_hook_advisory(self, tmp_memory):
        """Hook should advise when no memory activity today."""
        import subprocess
        import sys
        hook_path = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "memory-flush.py"
        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            cwd=str(tmp_memory),
            env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(tmp_memory)},
        )
        assert "ADVISORY" in result.stdout or "learning_review" in result.stdout

    def test_hook_quiet(self, tmp_memory):
        """Hook should be silent when memory activity exists today."""
        # Create a memory file with today's mtime (default)
        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        test_file = corrections_dir / "today-activity.yaml"
        test_file.write_text("id: test\ntype: correction\nsummary: test\n")

        import subprocess
        import sys
        hook_path = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "memory-flush.py"
        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            cwd=str(tmp_memory),
            env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(tmp_memory)},
        )
        assert "ADVISORY" not in result.stdout


class TestE2EFullLifecycle:
    """End-to-end: capture -> load -> reinforce -> pattern -> review -> apply -> excluded."""

    def test_full_lifecycle(self, tmp_memory, monkeypatch):
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        # Create command file for apply target
        commands_dir = tmp_memory / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        (commands_dir / "test-rule.md").write_text("# Test Rule\n\nExisting.\n")

        # 1. Capture
        r = capture_memory(type="correction", summary="Always check nulls before joining",
                          scope="universal", domain="billing", tables="billing_transactions",
                          investigation="inv-1")
        assert "Captured" in r

        # 2. Load
        r = load_relevant_memories(domain="billing", tables="billing_transactions")
        assert "check nulls" in r

        # 3. Reinforce to pattern
        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        with open(list(corrections_dir.glob("*.yaml"))[0]) as f:
            mem_id = yaml.safe_load(f)["id"]

        reinforce_memory(mem_id, session="inv-2")
        r = reinforce_memory(mem_id, session="inv-3")
        assert "Pattern detected" in r

        # 4. Learning review shows proposal
        r = learning_review()
        assert "Proposals" in r
        assert "Accept" in r

        # 5. Apply proposal
        r = apply_proposal(memory_id=mem_id, target_file=".claude/commands/test-rule.md",
                          action="append", content="Always check nulls before joining.",
                          scope="personal")
        assert "Applied" in r

        # 6. Promoted memory excluded from loading
        r = load_relevant_memories(domain="billing", tables="billing_transactions")
        assert "check nulls" not in r

        # 7. Stats shows promoted
        r = memory_stats()
        assert "promoted" in r


class TestE2EExpiration:
    """End-to-end: create old memories, run stats, verify decay/deletion."""

    def _create_memory(self, tmp_memory, **overrides):
        defaults = {
            "id": "correction-test", "type": "correction", "signal": "explicit_correction",
            "summary": "Test", "detail": None, "domain": "billing", "tables": [],
            "phase": "all", "scope": "universal", "times_reinforced": 1,
            "first_seen": date.today().isoformat(), "last_seen": date.today().isoformat(),
            "source_sessions": [], "status": "active", "promoted_to": None, "superseded_by": None,
        }
        defaults.update(overrides)
        type_dir = tmp_memory / ".claude" / "memory" / f"{defaults['type']}s"
        slug = defaults["id"].replace(f"{defaults['type']}-", "")
        filepath = type_dir / f"{slug}.yaml"
        suffix = 2
        while filepath.exists():
            filepath = type_dir / f"{slug}-{suffix}.yaml"
            suffix += 1
        with open(filepath, "w") as f:
            yaml.dump(defaults, f, default_flow_style=False, sort_keys=False)
        import os
        ls = defaults.get("last_seen", date.today().isoformat())
        if isinstance(ls, str):
            from datetime import datetime as dt
            ts = dt.strptime(ls, "%Y-%m-%d").timestamp()
            os.utime(filepath, (ts, ts))
        return filepath

    def test_mixed_expiration(self, tmp_memory):
        today = date.today().isoformat()
        d30 = (date.today() - timedelta(days=30)).isoformat()
        d65 = (date.today() - timedelta(days=65)).isoformat()
        d95 = (date.today() - timedelta(days=95)).isoformat()

        f_today = self._create_memory(tmp_memory, id="correction-today", last_seen=today)
        f_30d = self._create_memory(tmp_memory, id="correction-30d", last_seen=d30, first_seen=d30)
        f_65d = self._create_memory(tmp_memory, id="correction-65d", last_seen=d65, first_seen=d65)
        f_95d = self._create_memory(tmp_memory, id="correction-95d", last_seen=d95, first_seen=d95, status="decayed")
        f_promoted = self._create_memory(tmp_memory, id="correction-promoted", last_seen=d95, first_seen=d95, status="promoted")

        result = memory_stats()

        # Today and 30d: still active
        assert f_today.exists()
        with open(f_today) as f:
            assert yaml.safe_load(f)["status"] == "active"
        assert f_30d.exists()
        with open(f_30d) as f:
            assert yaml.safe_load(f)["status"] == "active"

        # 65d: decayed
        assert f_65d.exists()
        with open(f_65d) as f:
            assert yaml.safe_load(f)["status"] == "decayed"

        # 95d (was decayed): deleted
        assert not f_95d.exists()

        # Promoted: preserved
        assert f_promoted.exists()
        with open(f_promoted) as f:
            assert yaml.safe_load(f)["status"] == "promoted"


class TestE2EContradictionAndRollback:
    """End-to-end: capture -> promote -> contradict -> rollback proposal -> revert."""

    def test_contradiction_rollback_flow(self, tmp_memory, monkeypatch):
        import memory_mcp.tools.memory as memory_mod
        monkeypatch.setattr(memory_mod, "get_project_root", lambda: tmp_memory)

        # Setup command file
        commands_dir = tmp_memory / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        (commands_dir / "test-rule.md").write_text("# Test Rule\n\nExisting.\n")

        # 1. Capture and promote "always filter"
        capture_memory(type="correction", summary="Always filter status billing transactions",
                      scope="universal", tables="billing_transactions", investigation="inv-1")

        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        files = list(corrections_dir.glob("*.yaml"))
        with open(files[0]) as f:
            mem_id = yaml.safe_load(f)["id"]

        reinforce_memory(mem_id, session="inv-2")
        reinforce_memory(mem_id, session="inv-3")

        apply_proposal(memory_id=mem_id, target_file=".claude/commands/test-rule.md",
                      action="append", content="Always filter status billing transactions.",
                      scope="personal")

        # Verify promoted
        with open(files[0]) as f:
            assert yaml.safe_load(f)["status"] == "promoted"

        # 2. Capture contradiction
        r = capture_memory(type="correction", summary="Never filter status billing transactions for audit",
                          scope="universal", tables="billing_transactions", investigation="inv-4")
        assert "superseded" in r.lower() or "Captured" in r

        # 3. Learning review should flag rollback
        r = learning_review()
        assert "Rollback" in r
        assert "Revert" in r
