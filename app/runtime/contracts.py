"""Runtime contracts and protocol definitions."""

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from app.models.runtime_context import RuntimeContext
from app.models.tool_descriptor import ToolDescriptor
from app.models.tool_metadata import ToolMetadata
from app.tools.base_tool import BaseTool


@runtime_checkable
class ToolRegistryProtocol(Protocol):
    """Protocol governing the authoritative Tool Registry operations."""

    def register(self, tool: BaseTool) -> BaseTool:
        """Register a tool instance."""
        ...

    def resolve(self, tool_id: str, version: str | None = None) -> ToolDescriptor:
        """Resolve the ToolDescriptor for a tool_id."""
        ...

    def get(self, tool_id: str, version: str | None = None) -> BaseTool:
        """Retrieve an executable BaseTool instance."""
        ...

    def exists(self, tool_id: str) -> bool:
        """Check if a tool_id is registered."""
        ...

    def list_tools(self) -> tuple[BaseTool, ...]:
        """List all registered executable tools."""
        ...

    def discover_tools(self) -> tuple[ToolMetadata, ...]:
        """Discover tool metadata for registered tools."""
        ...


@runtime_checkable
class ToolFactoryProtocol(Protocol):
    """Protocol for creating/resolving tool instances."""

    def create_tool(self, tool_id: str, **kwargs: Any) -> BaseTool:
        """Instantiate or resolve a BaseTool by tool_id."""
        ...


@runtime_checkable
class ToolExecutorProtocol(Protocol):
    """Protocol for executing tool invocations within a runtime context."""

    def execute_tool(
        self,
        tool: BaseTool,
        parameters: Mapping[str, Any],
        context: RuntimeContext,
    ) -> Any:
        """Execute a tool with validated parameters and runtime context."""
        ...
