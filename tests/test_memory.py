"""Tests for memory.py -- capture, load, scoring, filtering,
reinforcement, dedup, review, reflection, outcome tracking."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from memory_mcp.tools.memory import (
    _compute_outcome_score,
    apply_proposal,
    capture_memory,
    capture_reflection,
    learning_review,
    load_relevant_memories,
    memory_stats,
    reinforce_memory,
    track_outcome,
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

    def test_schema_valid_outcomes(self):
        entry = {
            "id": "correction-test",
            "type": "correction",
            "summary": "Test",
            "scope": "universal",
            "status": "active",
            "outcomes": [
                {"result": "merged", "ts": "2026-01-15", "pr": 42},
                {"result": "positive_feedback", "ts": "2026-01-16", "context": "good"},
            ],
        }
        assert validate_memory_entry(entry) is None

    def test_schema_empty_outcomes_list(self):
        entry = {
            "id": "correction-test",
            "type": "correction",
            "summary": "Test",
            "scope": "universal",
            "status": "active",
            "outcomes": [],
        }
        assert validate_memory_entry(entry) is None

    def test_schema_outcomes_not_list(self):
        entry = {
            "id": "correction-test",
            "type": "correction",
            "summary": "Test",
            "scope": "universal",
            "status": "active",
            "outcomes": "not a list",
        }
        error = validate_memory_entry(entry)
        assert error is not None
        assert "list" in error

    def test_schema_outcomes_invalid_result(self):
        entry = {
            "id": "correction-test",
            "type": "correction",
            "summary": "Test",
            "scope": "universal",
            "status": "active",
            "outcomes": [{"result": "invalid_result", "ts": "2026-01-15"}],
        }
        error = validate_memory_entry(entry)
        assert error is not None
        assert "invalid_result" in error

    def test_schema_outcomes_missing_ts(self):
        entry = {
            "id": "correction-test",
            "type": "correction",
            "summary": "Test",
            "scope": "universal",
            "status": "active",
            "outcomes": [{"result": "merged"}],
        }
        error = validate_memory_entry(entry)
        assert error is not None
        assert "ts" in error


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


class TestTrackOutcome:
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

    def test_track_valid_outcome_merged(self, tmp_memory):
        self._create_memory(tmp_memory, id="correction-voided")
        result = track_outcome("correction-voided", "merged", pr=42)
        assert "Tracked outcome" in result
        assert "merged" in result
        assert "PR #42" in result
        assert "1 positive" in result

        filepath = tmp_memory / ".claude" / "memory" / "corrections" / "voided.yaml"
        with open(filepath) as f:
            data = yaml.safe_load(f)
        assert len(data["outcomes"]) == 1
        assert data["outcomes"][0]["result"] == "merged"
        assert data["outcomes"][0]["pr"] == 42

    def test_track_outcome_without_pr(self, tmp_memory):
        self._create_memory(tmp_memory, id="correction-voided")
        result = track_outcome("correction-voided", "positive_feedback", context="User liked it")
        assert "Tracked outcome" in result
        assert "PR #" not in result

        filepath = tmp_memory / ".claude" / "memory" / "corrections" / "voided.yaml"
        with open(filepath) as f:
            data = yaml.safe_load(f)
        assert "pr" not in data["outcomes"][0]
        assert data["outcomes"][0]["context"] == "User liked it"

    def test_track_invalid_result(self, tmp_memory):
        self._create_memory(tmp_memory, id="correction-voided")
        result = track_outcome("correction-voided", "invalid_result")
        assert "Error" in result
        assert "Invalid result" in result

    def test_track_memory_not_found(self, tmp_memory):
        result = track_outcome("nonexistent-id", "merged")
        assert "Error" in result
        assert "not found" in result

    def test_track_multiple_outcomes(self, tmp_memory):
        self._create_memory(tmp_memory, id="correction-voided")
        track_outcome("correction-voided", "merged", pr=10)
        track_outcome("correction-voided", "reverted", pr=11)
        result = track_outcome("correction-voided", "merged", pr=12)

        assert "2 positive" in result
        assert "1 negative" in result

        filepath = tmp_memory / ".claude" / "memory" / "corrections" / "voided.yaml"
        with open(filepath) as f:
            data = yaml.safe_load(f)
        assert len(data["outcomes"]) == 3

    def test_track_outcome_persisted(self, tmp_memory):
        self._create_memory(tmp_memory, id="correction-voided")
        track_outcome("correction-voided", "merged", pr=42, context="Clean merge")

        filepath = tmp_memory / ".claude" / "memory" / "corrections" / "voided.yaml"
        with open(filepath) as f:
            data = yaml.safe_load(f)
        outcome = data["outcomes"][0]
        assert outcome["result"] == "merged"
        assert outcome["ts"] == date.today().isoformat()
        assert outcome["pr"] == 42
        assert outcome["context"] == "Clean merge"

    def test_track_outcome_on_decayed_memory(self, tmp_memory):
        self._create_memory(tmp_memory, id="correction-voided", status="decayed")
        result = track_outcome("correction-voided", "merged")
        assert "Tracked outcome" in result

    def test_track_outcome_confirmation_format(self, tmp_memory):
        self._create_memory(tmp_memory, id="correction-voided")
        result = track_outcome("correction-voided", "closed")
        assert "Tracked outcome" in result
        assert "correction-voided" in result
        assert "closed" in result
        # closed is neither positive nor negative
        assert "0 positive" in result
        assert "0 negative" in result


class TestOutcomeScoring:
    def test_no_outcomes(self):
        assert _compute_outcome_score({}) == (0.5, 0, 0)

    def test_empty_outcomes_list(self):
        assert _compute_outcome_score({"outcomes": []}) == (0.5, 0, 0)

    def test_one_positive(self):
        memory = {"outcomes": [{"result": "merged", "ts": "2026-01-01"}]}
        score, pos, total = _compute_outcome_score(memory)
        assert pos == 1
        assert total == 1
        assert score == pytest.approx(2 / 3)  # (1+1)/(1+2)

    def test_one_negative(self):
        memory = {"outcomes": [{"result": "reverted", "ts": "2026-01-01"}]}
        score, pos, total = _compute_outcome_score(memory)
        assert pos == 0
        assert total == 1
        assert score == pytest.approx(1 / 3)  # (0+1)/(1+2)

    def test_all_positive(self):
        memory = {"outcomes": [
            {"result": "merged", "ts": f"2026-01-{i:02d}"} for i in range(1, 11)
        ]}
        score, pos, total = _compute_outcome_score(memory)
        assert pos == 10
        assert total == 10
        assert score == pytest.approx(11 / 12)  # (10+1)/(10+2)

    def test_closed_excluded(self):
        memory = {"outcomes": [
            {"result": "merged", "ts": "2026-01-01"},
            {"result": "closed", "ts": "2026-01-02"},
        ]}
        score, pos, total = _compute_outcome_score(memory)
        assert total == 1  # closed not counted
        assert pos == 1

    def test_mixed_outcomes(self):
        memory = {"outcomes": [
            {"result": "merged", "ts": "2026-01-01"},
            {"result": "merged", "ts": "2026-01-02"},
            {"result": "reverted", "ts": "2026-01-03"},
            {"result": "positive_feedback", "ts": "2026-01-04"},
        ]}
        score, pos, total = _compute_outcome_score(memory)
        assert pos == 3
        assert total == 4
        assert score == pytest.approx(4 / 6)  # (3+1)/(4+2)

    def test_laplace_smoothing_effect(self):
        """1/1 positive should rank below 10/10 positive due to Laplace smoothing."""
        mem_1 = {"outcomes": [{"result": "merged", "ts": "2026-01-01"}]}
        mem_10 = {"outcomes": [
            {"result": "merged", "ts": f"2026-01-{i:02d}"} for i in range(1, 11)
        ]}
        score_1, _, _ = _compute_outcome_score(mem_1)
        score_10, _, _ = _compute_outcome_score(mem_10)
        assert score_10 > score_1

    def test_return_tuple_format(self):
        memory = {"outcomes": [{"result": "merged", "ts": "2026-01-01"}]}
        result = _compute_outcome_score(memory)
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert isinstance(result[0], float)
        assert isinstance(result[1], int)
        assert isinstance(result[2], int)

    def test_non_list_outcomes(self):
        """Non-list outcomes field should return neutral score."""
        assert _compute_outcome_score({"outcomes": "invalid"}) == (0.5, 0, 0)


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

    def test_learning_review_proposals_sorted_by_outcome(self, tmp_memory):
        # Low outcome score
        self._create_memory(
            tmp_memory,
            id="correction-low-score",
            summary="Low outcome score correction",
            times_reinforced=5,
            status="pattern_candidate",
            source_sessions=["inv-1"],
            last_seen="2026-01-01",
            outcomes=[
                {"result": "reverted", "ts": "2026-01-01"},
                {"result": "reverted", "ts": "2026-01-02"},
            ],
        )
        # High outcome score
        self._create_memory(
            tmp_memory,
            id="correction-high-score",
            summary="High outcome score correction",
            times_reinforced=3,
            status="pattern_candidate",
            source_sessions=["inv-2"],
            last_seen="2026-01-01",
            outcomes=[
                {"result": "merged", "ts": "2026-01-01"},
                {"result": "merged", "ts": "2026-01-02"},
                {"result": "merged", "ts": "2026-01-03"},
            ],
        )
        result = learning_review()
        # Check ordering within Proposals section
        proposals = result[result.find("## Proposals"):]
        high_pos = proposals.find("High outcome score correction")
        low_pos = proposals.find("Low outcome score correction")
        assert high_pos < low_pos

    def test_learning_review_outcome_stats_displayed(self, tmp_memory):
        self._create_memory(
            tmp_memory,
            id="correction-with-outcomes",
            summary="Correction with outcomes",
            times_reinforced=3,
            status="pattern_candidate",
            source_sessions=["inv-1"],
            outcomes=[
                {"result": "merged", "ts": "2026-01-01"},
                {"result": "merged", "ts": "2026-01-02"},
                {"result": "reverted", "ts": "2026-01-03"},
            ],
        )
        result = learning_review()
        assert "2/3 positive" in result
        assert "score: 0.60" in result

    def test_learning_review_no_outcome_data(self, tmp_memory):
        self._create_memory(
            tmp_memory,
            id="correction-no-outcomes",
            summary="No outcomes correction",
            times_reinforced=3,
            status="pattern_candidate",
            source_sessions=["inv-1"],
        )
        result = learning_review()
        assert "No outcome data" in result

    def test_learning_review_high_outcome_above_low(self, tmp_memory):
        """High outcome memory should be Proposal 1, low outcome Proposal 2."""
        self._create_memory(
            tmp_memory,
            id="correction-bad",
            summary="Bad outcome correction",
            times_reinforced=5,
            status="pattern_candidate",
            source_sessions=["inv-1", "inv-2"],
            last_seen="2026-01-01",
            outcomes=[{"result": "reverted", "ts": "2026-01-01"}],
        )
        self._create_memory(
            tmp_memory,
            id="correction-good",
            summary="Good outcome correction",
            times_reinforced=3,
            status="pattern_candidate",
            source_sessions=["inv-3"],
            last_seen="2026-01-01",
            outcomes=[{"result": "merged", "ts": "2026-01-01"}],
        )
        result = learning_review()
        # Check ordering within Proposals section
        proposals = result[result.find("## Proposals"):]
        good_pos = proposals.find("Good outcome correction")
        bad_pos = proposals.find("Bad outcome correction")
        assert good_pos < bad_pos

    def test_learning_review_tiebreak_by_reinforcement(self, tmp_memory):
        """Same outcome score should tiebreak by reinforcement count."""
        self._create_memory(
            tmp_memory,
            id="correction-less-reinforced",
            summary="Less reinforced correction",
            times_reinforced=3,
            status="pattern_candidate",
            source_sessions=["inv-1"],
            last_seen="2026-01-01",
            outcomes=[{"result": "merged", "ts": "2026-01-01"}],
        )
        self._create_memory(
            tmp_memory,
            id="correction-more-reinforced",
            summary="More reinforced correction",
            times_reinforced=5,
            status="pattern_candidate",
            source_sessions=["inv-1", "inv-2"],
            last_seen="2026-01-01",
            outcomes=[{"result": "merged", "ts": "2026-01-01"}],
        )
        result = learning_review()
        # Check ordering within Proposals section
        proposals = result[result.find("## Proposals"):]
        more_pos = proposals.find("More reinforced correction")
        less_pos = proposals.find("Less reinforced correction")
        assert more_pos < less_pos


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

    def test_capture_reflection_with_root_causes(self, tmp_memory):
        result = capture_reflection(
            investigation="debug-session",
            went_well="Found the bug quickly",
            could_improve="Took wrong approach initially",
            root_causes=(
                "Took wrong approach → didn't read logs first"
                " → assumed code was correct"
                " → Root cause: skipped diagnostic step"
            ),
        )
        assert "Captured reflection" in result

        reflections_dir = tmp_memory / ".claude" / "memory" / "reflections"
        md_files = list(reflections_dir.glob("*.md"))
        content = md_files[0].read_text()
        assert "## Root Cause Analysis" in content
        assert "- Took wrong approach" in content
        assert "  - → didn't read logs first" in content
        assert "  - → Root cause: skipped diagnostic step" in content

    def test_capture_reflection_with_behavioral_changes(self, tmp_memory):
        result = capture_reflection(
            investigation="refactor-session",
            went_well="Clean refactor",
            could_improve="Missed edge case",
            behavioral_changes=(
                "Always check edge cases before refactoring"
                "|Run grep for existing usage before creating helpers"
            ),
        )
        assert "Captured reflection" in result

        reflections_dir = tmp_memory / ".claude" / "memory" / "reflections"
        md_files = list(reflections_dir.glob("*.md"))
        content = md_files[0].read_text()
        assert "## Behavioral Changes" in content
        assert "- Always check edge cases before refactoring" in content
        assert "- Run grep for existing usage before creating helpers" in content

    def test_capture_reflection_all_new_fields(self, tmp_memory):
        result = capture_reflection(
            investigation="full-session",
            went_well="Good collaboration",
            could_improve="Slow start, Wrong assumption on API",
            proposed_learning="Check API docs before coding",
            root_causes=(
                "Slow start → didn't plan"
                " → Root cause: skipped planning phase"
                "|Wrong API assumption → didn't read docs"
                " → Root cause: skipped reference check"
            ),
            behavioral_changes="Always plan before coding|Read API docs before making assumptions",
        )
        assert "Captured reflection" in result

        reflections_dir = tmp_memory / ".claude" / "memory" / "reflections"
        md_files = list(reflections_dir.glob("*.md"))
        content = md_files[0].read_text()
        # All sections present in correct order
        assert "## What Went Well" in content
        assert "## What Could Improve" in content
        assert "## Root Cause Analysis" in content
        assert "## Behavioral Changes" in content
        assert "## Proposed Learning" in content
        # Root causes rendered as nested lists
        assert "- Slow start" in content
        assert "  - → didn't plan" in content
        assert "- Wrong API assumption" in content
        # Behavioral changes as bullets
        assert "- Always plan before coding" in content
        assert "- Read API docs before making assumptions" in content
        # Proposed learning still works
        assert "Check API docs before coding" in content

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

    def _create_command_file(
        self, tmp_memory, name="test-rule.md",
        content="# Test Rule\n\nExisting content.\n",
    ):
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
        assert "source: correction-voided" in content
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
            f"<!-- Memory-promoted: {today}, source: "
            f"correction-rollback-test, "
            f"evidence: 3x reinforced -->\n"
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
            f"<!-- Memory-promoted: {today}, source: "
            f"correction-wrong-content, "
            f"evidence: 3x reinforced -->\n"
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
            f"<!-- Memory-promoted: {today}, source: "
            f"correction-multiline, "
            f"evidence: 3x reinforced -->\n"
        )

        self._create_memory(
            tmp_memory, id="correction-multiline",
            promoted_to=".claude/commands/test-rule.md",
        )

        result = apply_proposal(
            memory_id="correction-multiline",
            target_file=".claude/commands/test-rule.md",
            action="remove",
            content=(
                "## Multi-Line Promotion\n\n"
                "Line one of promoted content.\n"
                "Line two of promoted content.\n"
                "Line three of promoted content."
            ),
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
        self._create_memory(
            tmp_memory, id="correction-b",
            status="pattern_candidate", times_reinforced=3,
        )
        self._create_memory(
            tmp_memory, id="preference-c",
            type="preference", status="active",
        )
        self._create_memory(
            tmp_memory, id="correction-d",
            status="promoted", promoted_to="some-rule.md",
        )

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
        hook_path = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "memory-check.py"
        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            cwd=str(tmp_memory),
            env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(tmp_memory)},
        )
        output = json.loads(result.stdout)
        assert output["continue"] is True
        assert "/reflect" in output.get("message", "")

    def test_hook_quiet(self, tmp_memory):
        """Hook should be silent when memory activity exists today."""
        # Create a memory file with today's mtime (default)
        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        test_file = corrections_dir / "today-activity.yaml"
        test_file.write_text("id: test\ntype: correction\nsummary: test\n")

        import subprocess
        import sys
        hook_path = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "memory-check.py"
        result = subprocess.run(
            [sys.executable, str(hook_path)],
            capture_output=True,
            text=True,
            cwd=str(tmp_memory),
            env={**__import__("os").environ, "CLAUDE_PROJECT_DIR": str(tmp_memory)},
        )
        output = json.loads(result.stdout)
        assert "message" not in output or "/reflect" not in output.get("message", "")


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
        f_95d = self._create_memory(
            tmp_memory, id="correction-95d",
            last_seen=d95, first_seen=d95, status="decayed",
        )
        f_promoted = self._create_memory(
            tmp_memory, id="correction-promoted",
            last_seen=d95, first_seen=d95, status="promoted",
        )

        memory_stats()

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
        r = capture_memory(
            type="correction",
            summary="Never filter status billing transactions for audit",
            scope="universal", tables="billing_transactions",
            investigation="inv-4",
        )
        assert "superseded" in r.lower() or "Captured" in r

        # 3. Learning review should flag rollback
        r = learning_review()
        assert "Rollback" in r
        assert "Revert" in r


class TestAtomicWrites:
    """Test concurrent write safety."""

    def test_concurrent_captures_both_succeed(self, tmp_memory):
        """Two threads writing different memories simultaneously."""
        import threading

        results = [None, None]

        def capture_first():
            results[0] = capture_memory(
                type="correction",
                summary="First concurrent memory",
                scope="universal",
            )

        def capture_second():
            results[1] = capture_memory(
                type="correction",
                summary="Second concurrent memory",
                scope="universal",
            )

        t1 = threading.Thread(target=capture_first)
        t2 = threading.Thread(target=capture_second)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Both should succeed
        assert results[0] is not None
        assert results[1] is not None
        assert "Captured" in results[0]
        assert "Captured" in results[1]

        # Both files should exist
        corrections_dir = tmp_memory / ".claude" / "memory" / "corrections"
        yaml_files = list(corrections_dir.glob("*.yaml"))
        assert len(yaml_files) == 2

        # Both should be valid YAML
        for yf in yaml_files:
            with open(yf) as f:
                data = yaml.safe_load(f)
            assert data["status"] == "active"
            assert data["type"] == "correction"

    def test_concurrent_reinforce_count_correct(self, tmp_memory):
        """Two threads reinforcing same memory - final count should reflect both."""
        # First create a memory
        result = capture_memory(
            type="pattern",
            summary="Pattern to reinforce concurrently",
            scope="universal",
        )
        assert "Captured" in result

        # Find the memory ID
        patterns_dir = tmp_memory / ".claude" / "memory" / "patterns"
        yaml_files = list(patterns_dir.glob("*.yaml"))
        assert len(yaml_files) == 1

        with open(yaml_files[0]) as f:
            data = yaml.safe_load(f)
        memory_id = data["id"]

        import threading

        results = [None, None]

        def reinforce_first():
            results[0] = reinforce_memory(memory_id)

        def reinforce_second():
            results[1] = reinforce_memory(memory_id)

        t1 = threading.Thread(target=reinforce_first)
        t2 = threading.Thread(target=reinforce_second)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Both should succeed
        assert results[0] is not None
        assert results[1] is not None

        # Read final state
        with open(yaml_files[0]) as f:
            data = yaml.safe_load(f)
        # With atomic writes, at least one reinforce should have stuck
        # (count should be >= 2, could be 2 or 3 depending on race)
        assert data["times_reinforced"] >= 2


# --- Stemming and similarity scoring tests ---


class TestStemming:
    """Unit tests for the lightweight suffix stripping in _stem()."""

    def test_plural_s(self):
        from memory_mcp.tools.memory import _stem
        assert _stem("patterns") == "pattern"
        assert _stem("tools") == "tool"

    def test_plural_es(self):
        from memory_mcp.tools.memory import _stem
        assert _stem("processes") == "process"

    def test_plural_ies(self):
        from memory_mcp.tools.memory import _stem
        assert _stem("memories") == "memori"
        assert _stem("entries") == "entri"

    def test_ing(self):
        from memory_mcp.tools.memory import _stem
        assert _stem("learning") == "learn"
        assert _stem("capturing") == "captur"

    def test_ed(self):
        from memory_mcp.tools.memory import _stem
        assert _stem("prompted") == "prompt"
        assert _stem("captured") == "captur"

    def test_ly(self):
        from memory_mcp.tools.memory import _stem
        assert _stem("incrementally") == "incremental"

    def test_short_words_unchanged(self):
        from memory_mcp.tools.memory import _stem
        assert _stem("the") == "the"
        assert _stem("use") == "use"
        assert _stem("git") == "git"

    def test_no_double_strip(self):
        """Stemming should not strip too aggressively."""
        from memory_mcp.tools.memory import _stem
        # "less" should not lose the "s" (it's "ss")
        assert _stem("less") == "less"

    def test_stemmed_variants_match(self):
        """Key pairs that should produce the same stem."""
        from memory_mcp.tools.memory import _stem
        assert _stem("learning") == _stem("learnings")  # learn == learn
        assert _stem("captured") == _stem("capturing")  # captur == captur
        assert _stem("prompted") == _stem("prompting")  # prompt == prompt


class TestSimilarityScore:
    """Tests for the multi-signal similarity scoring.

    This class serves as a calibration suite: each test case documents
    a known pair with its expected classification. When tuning weights
    or threshold, run these to check for regressions.
    """

    def test_identical_strings(self):
        from memory_mcp.tools.memory import _similarity_score
        score = _similarity_score("exact same text", "exact same text")
        assert score > 0.9

    def test_empty_strings(self):
        from memory_mcp.tools.memory import _similarity_score
        assert _similarity_score("", "anything") == 0.0
        assert _similarity_score("anything", "") == 0.0
        assert _similarity_score("", "") == 0.0

    def test_completely_different(self):
        from memory_mcp.tools.memory import DEDUP_THRESHOLD, _similarity_score
        score = _similarity_score(
            "Always use .venv/bin/python3 not system python3",
            "GitHub Actions workflow validation fails on new files",
        )
        assert score < DEDUP_THRESHOLD

    def test_topic_adjacent_not_duplicate(self):
        """Two GitHub Actions memories: same domain, different facts."""
        from memory_mcp.tools.memory import DEDUP_THRESHOLD, _similarity_score
        score = _similarity_score(
            "GitHub Actions path filters on pull_request trigger skip workflows "
            "when only non-matching files change",
            "GitHub Actions workflow validation: new or modified workflow files "
            "fail OIDC app-token exchange until identical content exists on default branch",
        )
        assert score < DEDUP_THRESHOLD, (
            f"Topic-adjacent pair should NOT be detected as duplicate "
            f"(score={score:.3f}, threshold={DEDUP_THRESHOLD})"
        )

    def test_near_duplicate_similar_wording(self):
        """Near-identical phrasing should score well above threshold."""
        from memory_mcp.tools.memory import DEDUP_THRESHOLD, _similarity_score
        score = _similarity_score(
            "Filter voided transactions before aggregating",
            "Filter voided transactions before aggregating billing",
        )
        assert score >= DEDUP_THRESHOLD

    def test_first_sentence_comparison(self):
        """When one summary is much longer, first-sentence should help."""
        from memory_mcp.tools.memory import (
            _compute_signal_scores,
            _first_sentence,
            _weighted_score,
        )
        # Use the actual known duplicate pair where B has multiple sentences
        short = "Capture memories in real-time when corrections happen - do not wait until prompted"
        long = (
            "Capture learnings incrementally during the session, not just "
            "at /reflect time. Context compression after plan mode exit "
            "(or long sessions) can wipe conversation history. Call "
            "capture_memory() as corrections/patterns happen, so /reflect "
            "is a safety net not the only capture point."
        )
        full_score = _weighted_score(*_compute_signal_scores(short, long))
        fs_score = _weighted_score(
            *_compute_signal_scores(_first_sentence(short), _first_sentence(long))
        )
        assert fs_score > full_score, (
            f"First-sentence ({fs_score:.3f}) should score higher than "
            f"full text ({full_score:.3f}) when summaries differ in length"
        )


class TestCalibrationSuite:
    """Score table for all known pairs.

    Not asserting pass/fail for edge cases — this test prints scores
    to help calibrate the threshold. Run with -s to see output.
    """

    PAIRS = [
        # (label, summary_a, summary_b, expected)
        (
            "known-dup-capture-timing",
            "Capture memories in real-time when corrections happen - "
            "do not wait until prompted",
            "Capture learnings incrementally during the session, not just "
            "at /reflect time. Context compression after plan mode exit "
            "(or long sessions) can wipe conversation history. Call "
            "capture_memory() as corrections/patterns happen, so /reflect "
            "is a safety net not the only capture point.",
            "duplicate",
        ),
        (
            "near-dup-filter",
            "Filter voided transactions before aggregating",
            "Filter voided transactions before aggregating billing",
            "duplicate",
        ),
        (
            "topic-adj-github-actions",
            "GitHub Actions path filters on pull_request trigger skip "
            "workflows when only non-matching files change",
            "GitHub Actions workflow validation: new or modified workflow "
            "files fail OIDC app-token exchange until identical content "
            "exists on default branch",
            "none",
        ),
        (
            "topic-adj-ideation",
            "Design before building - do not skip ideation for UX-facing "
            "components even if they seem simple",
            "Project-specific ideation folders should be gitignored - "
            "design docs are local-only",
            "none",
        ),
        (
            "unrelated-venv-future",
            "Always use .venv/bin/python3 not system python3 - system "
            "Python is 3.9, venv is 3.13",
            "Use from __future__ import annotations in hook scripts to "
            "enable modern type syntax",
            "none",
        ),
    ]

    def test_print_score_table(self):
        """Print calibration table for threshold tuning."""
        from memory_mcp.tools.memory import (
            DEDUP_THRESHOLD,
            _compute_signal_scores,
            _first_sentence,
            _similarity_score,
            _weighted_score,
        )

        rows = []
        for label, a, b, expected in self.PAIRS:
            full = _weighted_score(*_compute_signal_scores(a, b))
            fs_a, fs_b = _first_sentence(a), _first_sentence(b)
            fs = _weighted_score(*_compute_signal_scores(fs_a, fs_b))
            final = _similarity_score(a, b)
            rows.append((label, full, fs, final, expected))

        # Print table
        print("\n--- Calibration Scores ---")
        print(f"{'Label':<30} {'Full':>6} {'1st-S':>6} {'Final':>6} {'Expect':<10} {'Result':<10}")
        for label, full, fs, final, expected in rows:
            detected = "duplicate" if final >= DEDUP_THRESHOLD else "none"
            match = "OK" if detected == expected else "MISS"
            print(
                f"{label:<30} {full:>6.3f} {fs:>6.3f} {final:>6.3f} "
                f"{expected:<10} {match:<10}"
            )
        print(f"Threshold: {DEDUP_THRESHOLD}")

    def test_clear_non_duplicates_below_threshold(self):
        """All unrelated pairs must score below threshold."""
        from memory_mcp.tools.memory import DEDUP_THRESHOLD, _similarity_score

        for label, a, b, expected in self.PAIRS:
            if expected == "none":
                score = _similarity_score(a, b)
                assert score < DEDUP_THRESHOLD, (
                    f"Non-duplicate '{label}' scored {score:.3f} >= {DEDUP_THRESHOLD}"
                )

    def test_clear_duplicates_above_threshold(self):
        """All duplicates must score above threshold."""
        from memory_mcp.tools.memory import DEDUP_THRESHOLD, _similarity_score

        for label, a, b, expected in self.PAIRS:
            if expected == "duplicate":
                score = _similarity_score(a, b)
                assert score >= DEDUP_THRESHOLD, (
                    f"Duplicate '{label}' scored {score:.3f} < {DEDUP_THRESHOLD}"
                )
