"""ToolExecutor — Dedicated runtime component for tool instantiation, execution, and exception translation.

ADR-023 execution invariant: the executor does not trust a caller's claimed
operation. It executes only when an ``ExecutionGrant`` issued by its bound
``ExecutionAuthority`` is authentic, unexpired and unconsumed, and the requested
operation exactly matches the grant's binding. Every other case fails closed with
``ExecutionBindingError`` before the tool is instantiated or run.
"""

from collections.abc import Mapping
from typing import Any

from app.models.execution_binding import (
    ExecutionBinding,
    ExecutionBindingValidationError,
)
from app.models.execution_grant import ExecutionGrant
from app.models.runtime_context import RuntimeContext
from app.models.tool_descriptor import ToolDescriptor
from app.runtime.execution_authority import (
    ExecutionAuthority,
    ExecutionBindingError,
    ExecutionRefusalReason,
)
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
    - Enforce the execution trust boundary: verify an ExecutionGrant against the
      requested operation before anything runs (ADR-023)
    - Instantiate BaseTool handles from passive ToolDescriptor objects
    - Execute the BaseTool instance with validated parameters and RuntimeContext
    - Translate unhandled runtime execution exceptions into ToolExecutionError

    RuntimeService answers "was this operation authorized?"; this executor
    independently answers "is this exactly the operation that was authorized?".
    An executor constructed without an authority refuses every execution.
    """

    def __init__(self, authority: ExecutionAuthority | None = None) -> None:
        self._authority = authority

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
        grant: ExecutionGrant | None = None,
    ) -> Any:
        """Verify the grant, then instantiate and execute a tool from a ToolDescriptor.

        A disabled tool is rejected before the grant is examined, so it cannot
        consume a grant it will never use.
        """
        if not descriptor.enabled:
            raise ToolDisabledError(f"Tool '{descriptor.tool_id}' is disabled")

        self._authorize(descriptor.tool_id, parameters, grant)
        tool = self.instantiate(descriptor)
        return self._run(tool, parameters)

    def execute_tool(
        self,
        tool: BaseTool,
        parameters: Mapping[str, Any],
        context: RuntimeContext | None = None,
        grant: ExecutionGrant | None = None,
    ) -> Any:
        """Verify the grant, then execute a BaseTool handle."""
        self._authorize(tool.tool_id, parameters, grant)
        return self._run(tool, parameters)

    def _authorize(
        self,
        tool_id: str,
        parameters: Mapping[str, Any],
        grant: ExecutionGrant | None,
    ) -> None:
        if self._authority is None:
            raise ExecutionBindingError(
                ExecutionRefusalReason.NO_AUTHORITY,
                tool_id,
                "executor is not bound to an execution authority",
            )

        if grant is None:
            raise ExecutionBindingError(ExecutionRefusalReason.MISSING_GRANT, tool_id)

        try:
            requested = ExecutionBinding.from_operation(
                tool_id=tool_id,
                parameters=parameters,
            )
        except ExecutionBindingValidationError as exc:
            raise ExecutionBindingError(
                ExecutionRefusalReason.INVALID_REQUEST,
                tool_id,
                str(exc),
            ) from exc

        self._authority.verify_and_consume(grant, requested)

    @staticmethod
    def _run(tool: BaseTool, parameters: Mapping[str, Any]) -> Any:
        try:
            return tool.execute(dict(parameters))
        except Exception as e:
            if isinstance(e, ToolExecutionError | ToolDisabledError):
                raise
            raise ToolExecutionError(tool.tool_id, str(e), cause=e) from e
