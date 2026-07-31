"""ToolService — Deprecated thin compatibility layer wrapping the authoritative ToolRegistry.

DEPRECATION NOTICE:
ToolService is an internal legacy compatibility wrapper. All new platform features,
management plane tools, and runtime resolution callers must interact directly with
ToolRegistry (app.registry.tool_registry.ToolRegistry). Do not add new functionality to this class.
"""

from app.models.tool import Tool
from app.registry.tool_registry import ToolRegistry


class ToolAlreadyExistsError(Exception):
    """Raised when attempting to register an existing tool."""


class ToolNotFoundError(Exception):
    """Raised when a tool cannot be found."""


class ToolService:
    """[DEPRECATED] Compatibility layer wrapping ToolRegistry for legacy API callers.

    All management plane queries and runtime execution lookups should interact directly
    with ToolRegistry.
    """

    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._tool_registry = tool_registry or ToolRegistry()

    def register_tool(self, tool: Tool) -> Tool:
        """Register a Tool descriptor in the compatibility service."""
        if tool.tool_id in self._tools or self._tool_registry.exists(tool.tool_id):
            raise ToolAlreadyExistsError(
                f"Tool '{tool.tool_id}' already exists"
            )

        self._tools[tool.tool_id] = tool
        return tool

    def get_tool(self, tool_id: str) -> Tool:
        """Retrieve a Tool descriptor by tool_id."""
        if tool_id in self._tools:
            return self._tools[tool_id]

        if self._tool_registry.exists(tool_id):
            metadata = self._tool_registry.resolve(tool_id).metadata
            return Tool(metadata=metadata)

        raise ToolNotFoundError(
            f"Tool '{tool_id}' not found"
        )

    def list_tools(self) -> list[Tool]:
        """List all managed Tool descriptors."""
        for metadata in self._tool_registry.discover_tools():
            t = Tool(metadata=metadata)
            if t.tool_id not in self._tools:
                self._tools[t.tool_id] = t
        return list(self._tools.values())