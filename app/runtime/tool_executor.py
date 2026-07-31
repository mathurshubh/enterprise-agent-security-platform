"""ToolExecutor — Dedicated runtime component for tool instantiation, execution, and exception translation."""

from collections.abc import Mapping
from typing import Any

from app.models.runtime_context import RuntimeContext
from app.models.tool_descriptor import ToolDescriptor
from app.tools.base_tool import BaseTool


class ToolExecutionError(Exception):
    """Raised when an unhandled exception occurs during tool execution."""

    def __init__(self, tool_id: str, message: str, cause: Exception | None = None) -> None:
        super().__init__(f"Execution failed for tool '{tool_id}': {message}")
        self.tool_id = tool_id
        self.cause = cause


class ToolDisabledError(Exception):
    """Raised when attempting to execute a disabled tool descriptor."""


class DefaultToolExecutor:
    """Dedicated runtime executor separating tool lookup/resolution from execution.

    Responsibilities:
    - Instantiate BaseTool handles from passive ToolDescriptor objects
    - Execute the BaseTool instance with validated parameters and RuntimeContext
    - Translate unhandled runtime execution exceptions into ToolExecutionError
    - Serve as a clean extension point for future telemetry, tracing, detection, and enforcement hooks
    """

    def instantiate(self, descriptor: ToolDescriptor, **kwargs: Any) -> BaseTool:
        """Instantiate or return an executable BaseTool handle from a passive ToolDescriptor."""
        if not descriptor.enabled:
            raise ToolDisabledError(f"Tool '{descriptor.tool_id}' is disabled")

        if descriptor.instance is not None:
            return descriptor.instance

        if descriptor.factory is not None:
            return descriptor.factory(**kwargs)

        raise ToolExecutionError(
            descriptor.tool_id, "Descriptor contains neither a BaseTool instance nor a factory"
        )

    def execute_descriptor(
        self,
        descriptor: ToolDescriptor,
        parameters: Mapping[str, Any],
        context: RuntimeContext | None = None,
    ) -> Any:
        """Instantiate and execute a tool from a ToolDescriptor."""
        tool = self.instantiate(descriptor)
        return self.execute_tool(tool, parameters, context)

    def execute_tool(
        self,
        tool: BaseTool,
        parameters: Mapping[str, Any],
        context: RuntimeContext | None = None,
    ) -> Any:
        """Execute a BaseTool handle with validated parameters and runtime context."""
        try:
            return tool.execute(dict(parameters))
        except Exception as e:
            if isinstance(e, ToolExecutionError | ToolDisabledError):
                raise
            raise ToolExecutionError(tool.tool_id, str(e), cause=e) from e
