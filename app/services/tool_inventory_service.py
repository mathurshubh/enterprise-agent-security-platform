from app.models.tool_metadata import ToolMetadata
from app.registry.tool_registry import ToolRegistry


class ToolInventoryService:
    """Read-only inventory view over registered executable tools."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
    ) -> None:
        self._tool_registry = tool_registry

    def list_registered_tools(self) -> tuple[ToolMetadata, ...]:
        return self._tool_registry.discover_tools()
