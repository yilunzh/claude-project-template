"""Tests for _registry.py -- tool registration, schema generation, retrieval."""

from memory_mcp.tools._registry import get_registered_tools, register_tool


class TestRegisterTool:
    def test_register_creates_entry(self):
        """Decorating a function should add it to the registry."""
        registry = get_registered_tools()
        # capture_memory should be registered (from memory.py import)
        assert "capture_memory" in registry

    def test_registered_entry_has_func(self):
        """Each registered entry should have a callable 'func'."""
        registry = get_registered_tools()
        for name, info in registry.items():
            assert "func" in info, f"Tool {name} missing 'func'"
            assert callable(info["func"]), f"Tool {name} func is not callable"

    def test_registered_entry_has_description(self):
        """Each registered entry should have a non-empty 'description'."""
        registry = get_registered_tools()
        for name, info in registry.items():
            assert "description" in info, f"Tool {name} missing 'description'"
            assert len(info["description"]) > 0, f"Tool {name} has empty description"

    def test_registered_entry_has_schema(self):
        """Each registered entry should have a well-formed 'schema'."""
        registry = get_registered_tools()
        for name, info in registry.items():
            schema = info["schema"]
            assert schema["type"] == "object", f"Tool {name} schema type != object"
            assert "properties" in schema, f"Tool {name} schema missing properties"
            assert "required" in schema, f"Tool {name} schema missing required"
            assert isinstance(schema["required"], list)

    def test_schema_properties_have_type_and_description(self):
        """Each property in a tool's schema should have type and description."""
        registry = get_registered_tools()
        for name, info in registry.items():
            for prop_name, prop_def in info["schema"]["properties"].items():
                assert "type" in prop_def, (
                    f"Tool {name}, param {prop_name} missing 'type'"
                )
                assert "description" in prop_def, (
                    f"Tool {name}, param {prop_name} missing 'description'"
                )

    def test_required_fields_are_subset_of_properties(self):
        """Required fields should all be defined in properties."""
        registry = get_registered_tools()
        for name, info in registry.items():
            prop_names = set(info["schema"]["properties"].keys())
            required = set(info["schema"]["required"])
            assert required.issubset(prop_names), (
                f"Tool {name}: required {required - prop_names} not in properties"
            )

    def test_get_registered_tools_returns_all_seven(self):
        """Should have exactly 7 tools registered."""
        registry = get_registered_tools()
        assert len(registry) == 7

    def test_tool_names_match_expected(self):
        """Registry should contain exactly the expected tool names."""
        registry = get_registered_tools()
        expected = {
            "capture_memory",
            "load_relevant_memories",
            "reinforce_memory",
            "learning_review",
            "capture_reflection",
            "apply_proposal",
            "memory_stats",
        }
        assert set(registry.keys()) == expected
