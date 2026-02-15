"""Tool registry for auto-generating MCP Tool schemas and call routing.

Each tool module registers its functions with schema metadata. The server
reads the registry to build the TOOLS list and call_tool dispatcher.
"""

from typing import Any, Callable

# Global registry: name -> {func, description, schema}
_TOOLS: dict[str, dict[str, Any]] = {}


def register_tool(
    name: str,
    description: str,
    parameters: dict[str, dict] | None = None,
    required: list[str] | None = None,
):
    """Decorator to register a function as an MCP tool.

    Args:
        name: Tool name (must be unique).
        description: Tool description shown to the AI.
        parameters: Dict of parameter definitions {name: {type, description}}.
        required: List of required parameter names.
    """
    def decorator(func: Callable) -> Callable:
        _TOOLS[name] = {
            "func": func,
            "description": description,
            "schema": {
                "type": "object",
                "properties": {
                    k: {"type": v.get("type", "string"), "description": v.get("description", "")}
                    for k, v in (parameters or {}).items()
                },
                "required": required or [],
            },
        }
        return func
    return decorator


def get_registered_tools() -> dict[str, dict[str, Any]]:
    """Return all registered tools."""
    return _TOOLS
