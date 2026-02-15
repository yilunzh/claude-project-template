"""Tests for the 3-stage harvester pipeline: extract_terms, diff_candidates, classify."""

import json
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

# The harvester scripts live at .claude/scripts/harvester/ which is a package
# (has __init__.py at both levels). Add .claude to sys.path so we can import
# them as scripts.harvester.<module>.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CLAUDE_DIR = _PROJECT_ROOT / ".claude"
if str(_CLAUDE_DIR) not in sys.path:
    sys.path.insert(0, str(_CLAUDE_DIR))

from scripts.harvester.classify import (  # noqa: E402, I001
    classify_all,
    classify_candidate,
    load_candidates,
    load_terms,
)
from scripts.harvester.diff_candidates import (  # noqa: E402
    build_section_policy_map,
    collect_file_candidates,
    collect_memory_candidates,
    diff_file,
    identify_changed_sections,
    parse_claude_md_sections,
    scan_memory_file,
)
from scripts.harvester.extract_terms import (  # noqa: E402
    _camel_to_terms,
    apply_custom_terms,
    compute_effective_terms,
    extract_all_terms,
    extract_terms_from_brief,
    extract_terms_from_dirname,
    extract_terms_from_filenames,
    extract_terms_from_python,
    load_existing_custom_terms,
)


# ===========================================================================
# extract_terms.py tests
# ===========================================================================


class TestCamelToTerms:
    def test_simple_camel_case(self):
        result = _camel_to_terms("UserProfile")
        assert "userprofile" in result
        assert "user" in result
        assert "profile" in result

    def test_multi_word(self):
        result = _camel_to_terms("BankImportTransaction")
        assert "bankimporttransaction" in result
        assert "bank" in result
        assert "import" in result
        assert "transaction" in result

    def test_single_word(self):
        result = _camel_to_terms("User")
        assert "user" in result

    def test_short_parts_excluded(self):
        # Parts shorter than _MIN_TERM_LENGTH (3) should be excluded
        result = _camel_to_terms("MyDB")
        assert "mydb" in result
        # "My" (2 chars) and "DB" (2 chars) are < 3 chars, should not appear
        assert "my" not in result


class TestExtractTermsFromBrief:
    def test_extracts_capitalized_phrases(self, tmp_path):
        brief = tmp_path / "BRIEF.md"
        brief.write_text("We are building the Bank Import Service.\n")
        result = extract_terms_from_brief(brief)
        assert "bank import service" in result

    def test_extracts_quoted_terms(self, tmp_path):
        brief = tmp_path / "BRIEF.md"
        brief.write_text('The "transaction ledger" tracks everything.\n')
        result = extract_terms_from_brief(brief)
        assert "transaction ledger" in result

    def test_extracts_is_a_pattern(self, tmp_path):
        brief = tmp_path / "BRIEF.md"
        brief.write_text(
            "ReconcileBot is a billing reconciliation tool for small businesses.\n"
        )
        result = extract_terms_from_brief(brief)
        assert "billing reconciliation tool" in result

    def test_extracts_capitalized_words(self, tmp_path):
        brief = tmp_path / "BRIEF.md"
        brief.write_text("The Dashboard shows Metrics for each Customer.\n")
        result = extract_terms_from_brief(brief)
        assert "dashboard" in result
        assert "metrics" in result
        assert "customer" in result

    def test_filters_stop_words(self, tmp_path):
        brief = tmp_path / "BRIEF.md"
        brief.write_text("- use the template to build an example project\n")
        result = extract_terms_from_brief(brief)
        # All words here are stop words
        for term in result:
            assert term not in {
                "use", "the", "template", "build", "example", "project",
            }

    def test_extracts_hyphenated_terms(self, tmp_path):
        brief = tmp_path / "BRIEF.md"
        brief.write_text("We need real-time event-driven processing.\n")
        result = extract_terms_from_brief(brief)
        assert "real-time" in result
        assert "event-driven" in result

    def test_extracts_from_bullet_points(self, tmp_path):
        brief = tmp_path / "BRIEF.md"
        brief.write_text(
            "- Support webhook notifications\n- Enable batch processing\n"
        )
        result = extract_terms_from_brief(brief)
        assert "webhook" in result
        assert "notifications" in result
        assert "batch" in result
        assert "processing" in result

    def test_skips_headers_and_blockquotes(self, tmp_path):
        brief = tmp_path / "BRIEF.md"
        brief.write_text("# MyHeader\n> Quoted text\n---\nActual Content here.\n")
        result = extract_terms_from_brief(brief)
        # "MyHeader" from header line should not be extracted
        assert "myheader" not in result

    def test_empty_file(self, tmp_path):
        brief = tmp_path / "BRIEF.md"
        brief.write_text("")
        result = extract_terms_from_brief(brief)
        assert result == []

    def test_missing_file(self, tmp_path):
        brief = tmp_path / "BRIEF.md"
        # File doesn't exist
        result = extract_terms_from_brief(brief)
        assert result == []


class TestExtractTermsFromDirname:
    def test_hyphen_separated(self, tmp_path):
        project = tmp_path / "my-cool-project"
        project.mkdir()
        result = extract_terms_from_dirname(project)
        assert "cool" in result
        assert "my-cool-project" in result

    def test_underscore_separated(self, tmp_path):
        project = tmp_path / "data_pipeline"
        project.mkdir()
        result = extract_terms_from_dirname(project)
        assert "data" in result
        assert "pipeline" in result
        assert "data_pipeline" in result

    def test_short_parts_excluded(self, tmp_path):
        project = tmp_path / "my-db"
        project.mkdir()
        result = extract_terms_from_dirname(project)
        # "my" and "db" are < 3 chars, excluded as individual terms
        assert "my" not in result


class TestExtractTermsFromPython:
    def test_extracts_class_names(self, tmp_path):
        src = tmp_path / "models.py"
        src.write_text(textwrap.dedent("""\
            class UserAccount:
                pass

            class PaymentGateway:
                pass
        """))
        result = extract_terms_from_python(tmp_path)
        assert "useraccount" in result
        assert "user" in result
        assert "account" in result
        assert "paymentgateway" in result
        assert "payment" in result
        assert "gateway" in result

    def test_extracts_dataclass_fields(self, tmp_path):
        src = tmp_path / "models.py"
        src.write_text(textwrap.dedent("""\
            from dataclasses import dataclass

            @dataclass
            class Invoice:
                invoice_number: str
                line_items: list
                total_amount: float
        """))
        result = extract_terms_from_python(tmp_path)
        assert "invoice" in result
        assert "invoice_number" in result
        assert "line_items" in result
        assert "total_amount" in result

    def test_skips_venv_directories(self, tmp_path):
        venv_file = tmp_path / ".venv" / "lib" / "site.py"
        venv_file.parent.mkdir(parents=True)
        venv_file.write_text("class ShouldBeIgnored:\n    pass\n")
        result = extract_terms_from_python(tmp_path)
        assert "shouldbeignored" not in result

    def test_handles_syntax_errors(self, tmp_path):
        bad_file = tmp_path / "broken.py"
        bad_file.write_text("class Incomplete(\n")
        # Should not raise
        result = extract_terms_from_python(tmp_path)
        assert isinstance(result, list)

    def test_no_python_files(self, tmp_path):
        result = extract_terms_from_python(tmp_path)
        assert result == []


class TestExtractTermsFromFilenames:
    def test_extracts_from_ts_files(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "user-profile.ts").write_text("")
        (src_dir / "payment_gateway.tsx").write_text("")
        result = extract_terms_from_filenames(tmp_path)
        assert "user" in result
        assert "profile" in result
        assert "payment" in result
        assert "gateway" in result

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "react"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("")
        result = extract_terms_from_filenames(tmp_path)
        assert "index" not in result
        assert "react" not in result


class TestCustomTerms:
    def test_apply_additions(self):
        auto = {"foo", "bar"}
        custom = ["+baz", "+qux"]
        result = apply_custom_terms(auto, custom)
        assert result == {"foo", "bar", "baz", "qux"}

    def test_apply_removals(self):
        auto = {"foo", "bar", "baz"}
        custom = ["-bar"]
        result = apply_custom_terms(auto, custom)
        assert result == {"foo", "baz"}

    def test_load_existing_custom_terms(self, tmp_path):
        output = tmp_path / "terms.yaml"
        output.write_text(yaml.dump({
            "terms": {
                "from_brief": ["alpha"],
                "custom": ["+beta", "-gamma"],
            }
        }))
        result = load_existing_custom_terms(output)
        assert result == ["+beta", "-gamma"]

    def test_load_nonexistent_file(self, tmp_path):
        result = load_existing_custom_terms(tmp_path / "missing.yaml")
        assert result == []


class TestExtractAllTerms:
    def test_combines_all_sources(self, tmp_path):
        brief = tmp_path / "BRIEF.md"
        brief.write_text("The Dashboard shows Analytics data.\n")
        output = tmp_path / "terms.yaml"

        result = extract_all_terms(tmp_path, output)
        assert result["source_project"] == tmp_path.name
        assert "extracted" in result
        assert "terms" in result
        terms = result["terms"]
        assert "from_brief" in terms
        assert "from_dirname" in terms
        assert "from_models" in terms
        assert "custom" in terms

    def test_compute_effective_terms(self):
        data = {
            "terms": {
                "from_brief": ["alpha", "beta"],
                "from_dirname": ["gamma"],
                "from_models": ["delta"],
                "custom": ["+epsilon", "-beta"],
            }
        }
        result = compute_effective_terms(data)
        assert result == {"alpha", "gamma", "delta", "epsilon"}


# ===========================================================================
# diff_candidates.py tests
# ===========================================================================


class TestParseClaudeMdSections:
    def test_template_managed_section(self):
        content = "## Development Workflow <!-- template-managed -->\nSome content.\n"
        result = parse_claude_md_sections(content)
        assert result["Development Workflow"] == "template-managed"

    def test_customizable_section(self):
        content = "## Project Overview <!-- customizable -->\nSome content.\n"
        result = parse_claude_md_sections(content)
        assert result["Project Overview"] == "customizable"

    def test_unmarked_section(self):
        content = "## My Section\nSome content.\n"
        result = parse_claude_md_sections(content)
        assert result["My Section"] == "unspecified"

    def test_multiple_sections(self):
        content = textwrap.dedent("""\
            ## Alpha <!-- template-managed -->
            Content A.
            ## Beta <!-- customizable -->
            Content B.
            ## Gamma
            Content C.
        """)
        result = parse_claude_md_sections(content)
        assert result == {
            "Alpha": "template-managed",
            "Beta": "customizable",
            "Gamma": "unspecified",
        }


class TestIdentifyChangedSections:
    def test_detects_changes_in_section(self):
        diff_lines = [
            "--- a/CLAUDE.md",
            "+++ b/CLAUDE.md",
            "@@ -1,5 +1,5 @@",
            " ## Alpha <!-- template-managed -->",
            "-old line",
            "+new line",
            " ## Beta <!-- customizable -->",
            " same content",
        ]
        policies = {"Alpha": "template-managed", "Beta": "customizable"}
        result = identify_changed_sections(diff_lines, policies)
        assert "Alpha" in result
        assert "Beta" not in result

    def test_changes_in_multiple_sections(self):
        diff_lines = [
            "--- a/CLAUDE.md",
            "+++ b/CLAUDE.md",
            "@@ -1,10 +1,10 @@",
            " ## First",
            "-removed",
            "+added",
            " ## Second",
            "+also added",
        ]
        policies = {"First": "unspecified", "Second": "unspecified"}
        result = identify_changed_sections(diff_lines, policies)
        assert "First" in result
        assert "Second" in result


class TestBuildSectionPolicyMap:
    def test_maps_changed_sections(self):
        changed = ["Alpha", "Gamma"]
        policies = {
            "Alpha": "template-managed",
            "Beta": "customizable",
            "Gamma": "unspecified",
        }
        result = build_section_policy_map(changed, policies)
        assert result == {"Alpha": "template-managed", "Gamma": "unspecified"}
        assert "Beta" not in result


class TestDiffFile:
    def test_both_missing(self, tmp_path):
        result = diff_file(
            tmp_path / "missing1.md", tmp_path / "missing2.md", "test.md"
        )
        assert result is None

    def test_new_file_in_project(self, tmp_path):
        proj = tmp_path / "project" / "new_hook.py"
        proj.parent.mkdir(parents=True)
        proj.write_text("print('hello')\n")
        tmpl = tmp_path / "template" / "new_hook.py"
        result = diff_file(proj, tmpl, ".claude/hooks/new_hook.py")
        assert result is not None
        assert result["change_type"] == "new_file"
        assert result["source"] == "file"

    def test_deleted_from_project(self, tmp_path):
        tmpl = tmp_path / "template" / "old_hook.py"
        tmpl.parent.mkdir(parents=True)
        tmpl.write_text("print('old')\n")
        proj = tmp_path / "project" / "old_hook.py"
        # Project file doesn't exist
        result = diff_file(proj, tmpl, ".claude/hooks/old_hook.py")
        assert result is None  # Deleted files are skipped

    def test_identical_files(self, tmp_path):
        content = "Same content\n"
        proj = tmp_path / "project" / "file.md"
        tmpl = tmp_path / "template" / "file.md"
        proj.parent.mkdir(parents=True)
        tmpl.parent.mkdir(parents=True)
        proj.write_text(content)
        tmpl.write_text(content)
        result = diff_file(proj, tmpl, "file.md")
        assert result is None

    def test_modified_file(self, tmp_path):
        proj = tmp_path / "project" / "hook.py"
        tmpl = tmp_path / "template" / "hook.py"
        proj.parent.mkdir(parents=True)
        tmpl.parent.mkdir(parents=True)
        tmpl.write_text("original\n")
        proj.write_text("modified\n")
        result = diff_file(proj, tmpl, ".claude/hooks/hook.py")
        assert result is not None
        assert result["change_type"] == "modified"
        assert result["diff_content"] != ""

    def test_claude_md_has_section_info(self, tmp_path):
        tmpl = tmp_path / "template" / "CLAUDE.md"
        proj = tmp_path / "project" / "CLAUDE.md"
        tmpl.parent.mkdir(parents=True)
        proj.parent.mkdir(parents=True)
        tmpl.write_text(textwrap.dedent("""\
            ## Overview <!-- customizable -->
            Template overview.
            ## Workflow <!-- template-managed -->
            Template workflow.
        """))
        proj.write_text(textwrap.dedent("""\
            ## Overview <!-- customizable -->
            My custom overview.
            ## Workflow <!-- template-managed -->
            Template workflow.
        """))
        result = diff_file(proj, tmpl, "CLAUDE.md")
        assert result is not None
        assert "Overview" in result["sections_changed"]
        assert result["section_policy"]["Overview"] == "customizable"


class TestCollectFileCandidates:
    def test_collects_from_file_pairs(self, tmp_path):
        proj = tmp_path / "project"
        tmpl = tmp_path / "template"
        proj.mkdir()
        tmpl.mkdir()

        # Create differing CLAUDE.md
        (proj / "CLAUDE.md").write_text("# Project\nCustom content.\n")
        (tmpl / "CLAUDE.md").write_text("# Project\nTemplate content.\n")

        candidates = collect_file_candidates(proj, tmpl)
        assert len(candidates) >= 1
        assert any(c["file_path"] == "CLAUDE.md" for c in candidates)

    def test_collects_from_hooks_dir(self, tmp_path):
        proj = tmp_path / "project"
        tmpl = tmp_path / "template"
        proj_hooks = proj / ".claude" / "hooks"
        tmpl_hooks = tmpl / "hooks"
        proj_hooks.mkdir(parents=True)
        tmpl_hooks.mkdir(parents=True)

        (proj_hooks / "my-hook.py").write_text("print('custom')\n")
        (tmpl_hooks / "my-hook.py").write_text("print('template')\n")

        candidates = collect_file_candidates(proj, tmpl)
        hook_candidates = [c for c in candidates if "hooks" in c["file_path"]]
        assert len(hook_candidates) >= 1


class TestScanMemoryFile:
    def test_active_memory(self, tmp_path):
        mem = tmp_path / "correction.yaml"
        mem.write_text(yaml.dump({
            "id": "corr-001",
            "type": "correction",
            "status": "active",
            "summary": "Filter voided transactions",
            "detail": "They inflate revenue",
            "scope": "universal",
            "times_reinforced": 2,
            "source_sessions": ["session-1"],
        }))
        result = scan_memory_file(mem)
        assert result is not None
        assert result["source"] == "memory"
        assert result["memory_id"] == "corr-001"
        assert result["times_reinforced"] == 2

    def test_pattern_candidate_memory(self, tmp_path):
        mem = tmp_path / "pattern.yaml"
        mem.write_text(yaml.dump({
            "id": "pat-001",
            "type": "pattern",
            "status": "pattern_candidate",
            "summary": "Use structured logging",
            "detail": "",
            "scope": "universal",
            "times_reinforced": 5,
        }))
        result = scan_memory_file(mem)
        assert result is not None
        assert result["type"] == "pattern"

    def test_promoted_memory_excluded(self, tmp_path):
        mem = tmp_path / "promoted.yaml"
        mem.write_text(yaml.dump({
            "id": "prom-001",
            "status": "promoted",
            "summary": "Already promoted",
        }))
        result = scan_memory_file(mem)
        assert result is None

    def test_decayed_memory_excluded(self, tmp_path):
        mem = tmp_path / "decayed.yaml"
        mem.write_text(yaml.dump({
            "id": "dec-001",
            "status": "decayed",
            "summary": "Old stuff",
        }))
        result = scan_memory_file(mem)
        assert result is None

    def test_invalid_yaml(self, tmp_path):
        mem = tmp_path / "bad.yaml"
        mem.write_text("{{invalid yaml::")
        result = scan_memory_file(mem)
        assert result is None


class TestCollectMemoryCandidates:
    def test_scans_subdirectories(self, tmp_path):
        mem_dir = tmp_path / ".claude" / "memory"
        for subdir in ["corrections", "preferences", "patterns"]:
            (mem_dir / subdir).mkdir(parents=True)

        (mem_dir / "corrections" / "c1.yaml").write_text(yaml.dump({
            "id": "c1",
            "type": "correction",
            "status": "active",
            "summary": "Test correction",
            "scope": "universal",
        }))
        (mem_dir / "patterns" / "p1.yaml").write_text(yaml.dump({
            "id": "p1",
            "type": "pattern",
            "status": "pattern_candidate",
            "summary": "Test pattern",
            "scope": "universal",
        }))

        candidates = collect_memory_candidates(tmp_path)
        assert len(candidates) == 2
        ids = {c["memory_id"] for c in candidates}
        assert ids == {"c1", "p1"}

    def test_no_memory_dir(self, tmp_path):
        candidates = collect_memory_candidates(tmp_path)
        assert candidates == []


# ===========================================================================
# classify.py tests
# ===========================================================================


class TestLoadCandidates:
    def test_load_valid_json(self, tmp_path):
        f = tmp_path / "candidates.json"
        data = [{"source": "memory", "tier": 1}]
        f.write_text(json.dumps(data))
        result = load_candidates(f)
        assert result == data

    def test_load_non_array(self, tmp_path):
        f = tmp_path / "candidates.json"
        f.write_text('{"not": "an array"}')
        with pytest.raises(ValueError, match="Expected JSON array"):
            load_candidates(f)

    def test_load_malformed_json(self, tmp_path):
        f = tmp_path / "candidates.json"
        f.write_text("{bad json!!")
        with pytest.raises(json.JSONDecodeError):
            load_candidates(f)


class TestLoadTerms:
    def test_load_terms_from_yaml(self, tmp_path):
        f = tmp_path / "terms.yaml"
        f.write_text(yaml.dump({
            "terms": {
                "from_brief": ["billing", "invoice"],
                "from_dirname": ["myapp"],
                "from_models": ["transaction"],
                "custom": ["+webhook", "-invoice"],
            }
        }))
        result = load_terms(f)
        assert "billing" in result
        assert "myapp" in result
        assert "transaction" in result
        assert "webhook" in result
        assert "invoice" not in result  # removed by custom

    def test_empty_terms_file(self, tmp_path):
        f = tmp_path / "terms.yaml"
        f.write_text(yaml.dump({"terms": {}}))
        result = load_terms(f)
        assert result == set()


class TestClassifyCandidate:
    def test_tier3_project_specific_term_in_summary(self):
        candidate = {
            "source": "memory",
            "summary": "Filter billing transactions carefully",
            "scope": "universal",
            "times_reinforced": 5,
        }
        terms = {"billing"}
        result = classify_candidate(candidate, terms)
        assert result["tier"] == 3
        assert "billing" in result["tier_reason"]

    def test_tier3_all_sections_customizable(self):
        candidate = {
            "source": "file",
            "file_path": "CLAUDE.md",
            "change_type": "modified",
            "section_policy": {
                "Overview": "customizable",
                "Constraints": "customizable",
            },
            "sections_changed": ["Overview", "Constraints"],
        }
        result = classify_candidate(candidate, set())
        assert result["tier"] == 3
        assert "customizable" in result["tier_reason"]

    def test_tier3_memory_non_universal_scope(self):
        candidate = {
            "source": "memory",
            "scope": "domain",
            "summary": "Use structured logging",
            "times_reinforced": 10,
        }
        result = classify_candidate(candidate, set())
        assert result["tier"] == 3
        assert "domain" in result["tier_reason"]

    def test_tier3_investigation_scope(self):
        candidate = {
            "source": "memory",
            "scope": "investigation",
            "summary": "Temp finding",
            "times_reinforced": 1,
        }
        result = classify_candidate(candidate, set())
        assert result["tier"] == 3

    def test_tier3_one_time_scope(self):
        candidate = {
            "source": "memory",
            "scope": "one_time",
            "summary": "One-off correction",
            "times_reinforced": 0,
        }
        result = classify_candidate(candidate, set())
        assert result["tier"] == 3

    def test_tier1_universal_reinforced_no_project_terms(self):
        candidate = {
            "source": "memory",
            "scope": "universal",
            "summary": "Always validate input data",
            "detail": "Prevents downstream errors",
            "times_reinforced": 5,
        }
        result = classify_candidate(candidate, set())
        assert result["tier"] == 1
        assert "Universal memory" in result["tier_reason"]
        assert "5x reinforced" in result["tier_reason"]
        assert result["skip_reason"] is None

    def test_tier1_exact_threshold(self):
        """Exactly 3x reinforcement should qualify for Tier 1."""
        candidate = {
            "source": "memory",
            "scope": "universal",
            "summary": "Always validate input data",
            "times_reinforced": 3,
        }
        result = classify_candidate(candidate, set())
        assert result["tier"] == 1

    def test_tier1_requires_3x_reinforcement(self):
        candidate = {
            "source": "memory",
            "scope": "universal",
            "summary": "Always validate input data",
            "times_reinforced": 2,
        }
        result = classify_candidate(candidate, set())
        # 2x reinforcement is below threshold, should be Tier 2
        assert result["tier"] == 2

    def test_tier2_universal_under_reinforcement_threshold(self):
        candidate = {
            "source": "memory",
            "scope": "universal",
            "summary": "Generic advice",
            "times_reinforced": 1,
        }
        result = classify_candidate(candidate, set())
        assert result["tier"] == 2
        assert "below reinforcement threshold" in result["tier_reason"]

    def test_tier2_file_diff(self):
        candidate = {
            "source": "file",
            "file_path": ".claude/hooks/my-hook.py",
            "change_type": "modified",
            "sections_changed": [],
            "section_policy": {},
            "diff_content": "some diff",
        }
        result = classify_candidate(candidate, set())
        assert result["tier"] == 2
        assert "File diff" in result["tier_reason"]

    def test_tier2_new_file_without_project_terms(self):
        candidate = {
            "source": "file",
            "file_path": ".claude/hooks/new-hook.py",
            "change_type": "new_file",
            "sections_changed": [],
            "section_policy": {},
            "diff_content": "",
        }
        result = classify_candidate(candidate, set())
        assert result["tier"] == 2

    def test_project_term_in_diff_content(self):
        candidate = {
            "source": "file",
            "file_path": ".claude/hooks/hook.py",
            "change_type": "modified",
            "sections_changed": [],
            "section_policy": {},
            "diff_content": "Check the billing module for errors",
        }
        terms = {"billing"}
        result = classify_candidate(candidate, terms)
        assert result["tier"] == 3

    def test_mixed_section_policies_not_all_customizable(self):
        candidate = {
            "source": "file",
            "file_path": "CLAUDE.md",
            "change_type": "modified",
            "section_policy": {
                "Overview": "customizable",
                "Workflow": "template-managed",
            },
            "sections_changed": ["Overview", "Workflow"],
        }
        result = classify_candidate(candidate, set())
        # Not all customizable, so shouldn't be Tier 3 from that rule
        assert result["tier"] == 2

    def test_preserves_original_fields(self):
        candidate = {
            "source": "memory",
            "scope": "universal",
            "summary": "Test",
            "times_reinforced": 5,
            "extra_field": "preserved",
        }
        result = classify_candidate(candidate, set())
        assert result["extra_field"] == "preserved"
        assert result["source"] == "memory"


class TestClassifyAll:
    def test_classifies_multiple_candidates(self):
        candidates = [
            {
                "source": "memory",
                "scope": "universal",
                "summary": "Always validate",
                "times_reinforced": 5,
            },
            {
                "source": "memory",
                "scope": "domain",
                "summary": "Domain specific",
                "times_reinforced": 1,
            },
            {
                "source": "file",
                "file_path": "CLAUDE.md",
                "change_type": "modified",
                "section_policy": {"Overview": "customizable"},
                "sections_changed": ["Overview"],
            },
        ]
        results = classify_all(candidates, set())
        tiers = [r["tier"] for r in results]
        assert tiers == [1, 3, 3]

    def test_empty_candidates(self):
        results = classify_all([], set())
        assert results == []
