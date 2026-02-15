"""Tests for server.py -- MCP server dispatch, tool building, error handling."""

import asyncio
from unittest.mock import patch

import pytest

from memory_mcp.server import _build_tools, call_tool, TOOLS
from memory_mcp.tools._registry import get_registered_tools


EXPECTED_TOOL_NAMES = {
    "capture_memory",
    "load_relevant_memories",
    "reinforce_memory",
    "learning_review",
    "capture_reflection",
    "apply_proposal",
    "memory_stats",
}


class TestBuildTools:
    def test_build_tools_returns_all_registered(self):
        """_build_tools should return a Tool for every registered tool."""
        tools = _build_tools()
        tool_names = {t.name for t in tools}
        assert tool_names == EXPECTED_TOOL_NAMES

    def test_build_tools_count(self):
        """TOOLS module-level list should have 7 entries."""
        assert len(TOOLS) == 7

    def test_build_tools_have_descriptions(self):
        """Every tool should have a non-empty description."""
        for tool in TOOLS:
            assert tool.description, f"Tool {tool.name} has no description"
            assert len(tool.description) > 10, f"Tool {tool.name} description too short"

    def test_build_tools_have_schemas(self):
        """Every tool should have an inputSchema with 'type' and 'properties'."""
        for tool in TOOLS:
            schema = tool.inputSchema
            assert schema["type"] == "object"
            assert "properties" in schema


class TestCallTool:
    """Test the async call_tool dispatcher."""

    def _run(self, coro):
        """Helper to run an async coroutine."""
        return asyncio.run(coro)

    def test_call_tool_unknown_tool(self):
        """Unknown tool name should return an error message."""
        result = self._run(call_tool("nonexistent_tool", {}))
        assert len(result) == 1
        assert "Unknown tool" in result[0].text
        assert "nonexistent_tool" in result[0].text

    def test_call_tool_missing_required_arg(self):
        """Missing a required argument should return an error."""
        # capture_memory requires: type, summary, scope
        result = self._run(call_tool("capture_memory", {"type": "correction"}))
        assert len(result) == 1
        assert "Missing required argument" in result[0].text

    def test_call_tool_dispatches_successfully(self, tmp_memory):
        """A valid call should dispatch to the tool and return a result."""
        result = self._run(call_tool("capture_memory", {
            "type": "correction",
            "summary": "Server dispatch test",
            "scope": "universal",
        }))
        assert len(result) == 1
        assert "Captured" in result[0].text
        assert "Server dispatch test" in result[0].text

    def test_call_tool_handles_exception(self):
        """If the tool function raises, call_tool should catch and return error."""
        registry = get_registered_tools()

        # Temporarily replace a tool's function with one that raises
        original_func = registry["memory_stats"]["func"]
        registry["memory_stats"]["func"] = lambda: (_ for _ in ()).throw(
            RuntimeError("test explosion")
        )
        try:
            result = self._run(call_tool("memory_stats", {}))
            assert len(result) == 1
            assert "Error" in result[0].text
            assert "test explosion" in result[0].text
        finally:
            # Restore original
            registry["memory_stats"]["func"] = original_func

    def test_call_tool_optional_args_omitted(self, tmp_memory):
        """Optional arguments should not be required."""
        # load_relevant_memories has all optional params
        result = self._run(call_tool("load_relevant_memories", {}))
        assert len(result) == 1
        # Should work (returns "No relevant memories" or similar)
        assert result[0].text  # Non-empty response

    def test_call_tool_returns_text_content(self, tmp_memory):
        """Result should always be a list of TextContent."""
        result = self._run(call_tool("memory_stats", {}))
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[0].type == "text"
        assert isinstance(result[0].text, str)
