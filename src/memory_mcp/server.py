"""MCP Server for agent memory system.

Provides tools for capturing behavioral learnings, loading relevant context,
reinforcing patterns, and promoting mature learnings to rules/skills.

Tools are registered via the _registry decorator pattern. Each tool module
registers its functions on import. The server auto-builds the MCP Tool list
and call_tool dispatcher from the registry.
"""

import asyncio
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import all tool modules to trigger registration
from . import tools  # noqa: F401
from .tools._registry import get_registered_tools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("memory-mcp")

# Create the MCP server
server = Server("memory-mcp")


def _build_tools() -> list[Tool]:
    """Build MCP Tool list from the registry."""
    return [
        Tool(
            name=name,
            description=info["description"],
            inputSchema=info["schema"],
        )
        for name, info in get_registered_tools().items()
    ]


TOOLS = _build_tools()


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return the list of available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls by dispatching to the registered function."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")

    registry = get_registered_tools()
    if name not in registry:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    try:
        func = registry[name]["func"]
        schema = registry[name]["schema"]

        # Build kwargs from arguments, matching function parameters
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        kwargs = {}
        for param_name in properties:
            if param_name in arguments:
                kwargs[param_name] = arguments[param_name]
            elif param_name in required:
                return [TextContent(
                    type="text",
                    text=f"Missing required argument: {param_name}",
                )]

        result = func(**kwargs)
        return [TextContent(type="text", text=result)]

    except Exception as e:
        logger.error(f"Error executing tool {name}: {str(e)}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the MCP server."""
    logger.info("Starting Memory MCP Server...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run():
    """Entry point for running the server."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
