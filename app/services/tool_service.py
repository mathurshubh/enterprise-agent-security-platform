from app.models.tool import Tool


class ToolAlreadyExistsError(Exception):
    """Raised when attempting to register an existing tool."""


class ToolNotFoundError(Exception):
    """Raised when a tool cannot be found."""


class ToolService:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register_tool(self, tool: Tool) -> Tool:
        if tool.tool_id in self._tools:
            raise ToolAlreadyExistsError(
                f"Tool '{tool.tool_id}' already exists"
            )

        self._tools[tool.tool_id] = tool
        return tool

    def get_tool(self, tool_id: str) -> Tool:
        if tool_id not in self._tools:
            raise ToolNotFoundError(
                f"Tool '{tool_id}' not found"
            )

        return self._tools[tool_id]

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())