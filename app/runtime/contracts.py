"""Runtime contracts and protocol definitions."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.models.audit_event import Decision
from app.models.execution_binding import ExecutionBinding
from app.models.execution_capability import ExecutionCapabilities
from app.models.execution_provenance import ExecutionProvenance
from app.models.execution_receipt import (
    ExecutionReceipt,
    ExecutionStatus,
    ReconciliationReason,
)
from app.models.runtime_context import RuntimeContext
from app.models.runtime_execution_grant import RuntimeExecutionGrant
from app.models.sandbox_execution_result import SandboxExecutionResult
from app.models.tool_descriptor import ToolDescriptor
from app.models.tool_metadata import ToolMetadata
from app.tools.base_tool import BaseTool


@runtime_checkable
class ExecutionAuthorityProtocol(Protocol):
    """Protocol governing the execution trust boundary's authority (ADR-023).

    The executor previously discovered this surface with ``hasattr``, which made the
    "verification precedes execution" invariant depend on whichever methods the
    concrete object happened to expose: an authority with ``consume_grant`` but no
    ``verify_grant`` would have executed with verification silently skipped. Requiring
    the contract makes the invariant structural rather than incidental.
    """

    @property
    def authority_id(self) -> str:
        """Identifier of this authority, used to reject foreign grants."""
        ...

    def issue(
        self,
        binding: ExecutionBinding,
        decision: Decision,
        *,
        agent_id: str,
        session_id: str,
        expected_epoch: int | None = None,
        capability_profile_id: str | None = None,
        capability_digest: str | None = None,
    ) -> RuntimeExecutionGrant | None:
        """Issue a grant for ``binding`` if and only if it may be authorized."""
        ...

    def verify_grant(self, grant: object, requested: ExecutionBinding) -> None:
        """Verify that ``grant`` authorizes exactly ``requested`` without consuming it."""
        ...

    def consume_grant(self, grant: RuntimeExecutionGrant) -> None:
        """Atomically consume an outstanding grant."""
        ...

    def verify_and_consume(self, grant: object, requested: ExecutionBinding) -> None:
        """Verify that ``grant`` authorizes exactly ``requested``, then consume it."""
        ...


@runtime_checkable
class ToolExecutionSandboxProtocol(Protocol):
    """Protocol governing physical tool execution isolation (ADR-032)."""

    def execute(
        self,
        *,
        tool: BaseTool,
        parameters: Mapping[str, Any],
        capabilities: ExecutionCapabilities,
        provenance: ExecutionProvenance,
    ) -> SandboxExecutionResult:
        """Execute an authorized tool within the isolated sandbox environment.

        ``provenance`` is derived from the verified grant. The sandbox receives no
        caller-supplied ``RuntimeContext``: it needs identity only to label the child
        payload, and unsigned identity has no place at an enforcement boundary.
        """
        ...


@runtime_checkable
class CapabilityProfileRegistryProtocol(Protocol):
    """Protocol governing resolution of immutable ExecutionCapabilities profiles (ADR-032)."""

    def resolve_profile(self, profile_id: str) -> ExecutionCapabilities:
        """Resolve an ExecutionCapabilities profile by profile_id."""
        ...

    def register_profile(self, capabilities: ExecutionCapabilities) -> None:
        """Register an immutable ExecutionCapabilities profile."""
        ...

    def exists(self, profile_id: str) -> bool:
        """Whether a profile is registered under ``profile_id``."""
        ...



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
    """Authoritative protocol for persisting and querying execution receipts.

    Invariants enumerated in ADR-032 §12.1. No production path supplies an evidence
    store today, so these govern an implemented and tested capability that is not yet
    on the production execution path (ADR-026, NEW-003).

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
        request_id: str,
        tool_id: str,
        binding_hash: str,
        capability_profile_id: str,
        capability_digest: str,
        declared_timeout_seconds: float,
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

    def get_monotonic_start(self, receipt_id: str) -> float | None:
        """Monotonic start recorded for an in-flight receipt, or None if unavailable.

        Reconciliation depends on this to evaluate each receipt against its own declared
        execution budget. ``None`` means the timing evidence is genuinely missing, which
        is itself a reconcilable condition; a store that cannot answer at all is a
        contract violation, not a store whose executions are all unrecoverable.
        """
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
