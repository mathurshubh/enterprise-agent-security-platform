from app.tools.base_tool import BaseTool


class DuplicateToolRegistrationError(Exception):
    """Raised when a tool is already registered."""


class ToolNotRegisteredError(Exception):
    """Raised when a tool is not registered."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(
        self,
        tool: BaseTool,
    ) -> BaseTool:
        tool_id = tool.tool_id

        if tool_id in self._tools:
            raise DuplicateToolRegistrationError(
                f"Tool '{tool_id}' is already registered"
            )

        self._tools[tool_id] = tool
        return tool

    def get(
        self,
        tool_id: str,
    ) -> BaseTool:
        if tool_id not in self._tools:
            raise ToolNotRegisteredError(
                f"Tool '{tool_id}' is not registered"
            )

        return self._tools[tool_id]

    def exists(
        self,
        tool_id: str,
    ) -> bool:
        return tool_id in self._tools

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())
