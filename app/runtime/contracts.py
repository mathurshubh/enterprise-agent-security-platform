"""Runtime contracts and protocol definitions."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.models.execution_receipt import (
    ExecutionReceipt,
    ExecutionStatus,
    ReconciliationReason,
)
from app.models.runtime_context import RuntimeContext
from app.models.runtime_execution_grant import RuntimeExecutionGrant
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
        grant: RuntimeExecutionGrant | None = None,
    ) -> Any:
        """Execute a tool only if ``grant`` authorizes exactly this operation (ADR-023)."""
        ...


@runtime_checkable
class ExecutionEvidenceStoreProtocol(Protocol):
    """Authoritative protocol for persisting and querying execution receipts (NEW-003).

    Transition semantics:
    - record_started(): Creates initial STARTED receipt. Rejects if receipt_id or
      grant_id already exists (N3-9).
    - record_terminal(): Transitions an open (STARTED) receipt to an observed terminal
      state: SUCCEEDED, FAILED, TIMEOUT, or INTERRUPTED. Rejects UNKNOWN (reconciliation
      only) and transitions on already-terminal receipts (N3-4).
    - record_reconciled(): Reconciliation authority. Transitions an open (STARTED) receipt
      to UNKNOWN with a ReconciliationReason (N3-5).
    """

    def record_started(
        self,
        *,
        receipt_id: str,
        grant_id: str,
        session_id: str,
        agent_id: str,
        tool_id: str,
        binding_hash: str,
        started_at: datetime,
        monotonic_start: float | None = None,
    ) -> ExecutionReceipt:
        """Record initial STARTED receipt. Raises on store capacity, duplicate, or integrity failure."""
        ...

    def record_terminal(
        self,
        *,
        receipt_id: str,
        status: ExecutionStatus,
        completed_at: datetime,
        duration_ms: int,
        error_type: str | None = None,
        error_code: str | None = None,
        output_digest: str | None = None,
    ) -> ExecutionReceipt:
        """Transition an open receipt to an observed terminal state (SUCCEEDED, FAILED, TIMEOUT, INTERRUPTED)."""
        ...

    def record_reconciled(
        self,
        *,
        receipt_id: str,
        reconciled_at: datetime,
        reason: ReconciliationReason,
    ) -> ExecutionReceipt:
        """Reconciliation authority: transition an open (STARTED) receipt to UNKNOWN."""
        ...

    def get(self, receipt_id: str) -> ExecutionReceipt | None:
        """Retrieve receipt by receipt_id."""
        ...

    def get_by_grant(self, grant_id: str) -> ExecutionReceipt | None:
        """Retrieve receipt associated with a specific grant_id."""
        ...

    def list_open(self) -> tuple[ExecutionReceipt, ...]:
        """List all currently unresolved (STARTED) receipts."""
        ...

    def list_receipts(
        self,
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> tuple[ExecutionReceipt, ...]:
        """List receipts filtered by session or agent."""
        ...
