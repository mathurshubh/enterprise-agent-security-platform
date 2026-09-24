"""ToolExecutor — Dedicated runtime component for tool instantiation, execution, and exception translation.

ADR-023 execution invariant: the executor does not trust a caller's claimed
operation. It executes only when an ``ExecutionGrant`` issued by its bound
``ExecutionAuthority`` is authentic, unexpired and unconsumed, and the requested
operation exactly matches the grant's binding. Every other case fails closed with
``ExecutionBindingError`` before the tool is instantiated or run.

NEW-003 invariants:
- N3-1 (Provenance): Derives identity and binding exclusively from the verified grant/context.
- N3-2 (Grant/Execution Separation): Consuming a grant does not imply execution started or succeeded.
- N3-3 (Trusted Boundary): STARTED evidence established before invoking tool; store failure fails closed.
- N3-6 (Evidence/Telemetry Separation): Evidence store is authoritative; telemetry is operational projection.
- N3-7 (Diagnostic Safety): Raw exception messages excluded from durable evidence.
- N3-8 (Governance Independence): Execution failure does not mutate the prior ALLOW decision.
"""

import hashlib
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.models.execution_binding import (
    ExecutionBinding,
    ExecutionBindingValidationError,
)
from app.models.execution_receipt import (
    ExecutionStatus,
    compute_output_digest,
)
from app.models.runtime_context import RuntimeContext
from app.models.runtime_execution_grant import RuntimeExecutionGrant
from app.models.telemetry.behavioral_event import BehavioralEvent
from app.models.telemetry.event_taxonomy import TelemetryEventType
from app.models.tool_descriptor import ToolDescriptor
from app.runtime.contracts import ExecutionEvidenceStoreProtocol
from app.runtime.execution_authority import (
    ExecutionAuthority,
    ExecutionBindingError,
    ExecutionRefusalReason,
)
from app.tools.base_tool import BaseTool


class ToolExecutionError(Exception):
    """Raised when an unhandled exception occurs during tool execution."""

    def __init__(
        self, tool_id: str, message: str, cause: Exception | None = None
    ) -> None:
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
    - Record authoritative execution boundary evidence (NEW-003)

    RuntimeService answers "was this operation authorized?"; this executor
    independently answers "is this exactly the operation that was authorized?".
    An executor constructed without an authority refuses every execution.
    """

    def __init__(
        self,
        authority: ExecutionAuthority | None = None,
        evidence_store: ExecutionEvidenceStoreProtocol | None = None,
        telemetry_emitter: Any | None = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._authority = authority
        self._evidence_store = evidence_store
        self._telemetry_emitter = telemetry_emitter
        self._monotonic_clock = monotonic_clock

    def instantiate(self, descriptor: ToolDescriptor, **kwargs: Any) -> BaseTool:
        """Instantiate or return an executable BaseTool handle from a passive ToolDescriptor."""
        if not descriptor.enabled:
            raise ToolDisabledError(f"Tool '{descriptor.tool_id}' is disabled")

        if descriptor.instance is not None:
            return descriptor.instance

        if descriptor.factory is not None:
            return descriptor.factory(**kwargs)

        raise ToolExecutionError(
            descriptor.tool_id,
            "Descriptor contains neither a BaseTool instance nor a factory",
        )

    def execute_descriptor(
        self,
        descriptor: ToolDescriptor,
        parameters: Mapping[str, Any],
        context: RuntimeContext | None = None,
        grant: RuntimeExecutionGrant | None = None,
    ) -> Any:
        """Verify the grant, then instantiate and execute a tool from a ToolDescriptor.

        A disabled tool is rejected before the grant is examined, so it cannot
        consume a grant it will never use.
        """
        if not descriptor.enabled:
            raise ToolDisabledError(f"Tool '{descriptor.tool_id}' is disabled")

        self._authorize(descriptor.tool_id, parameters, grant)
        tool = self.instantiate(descriptor)
        return self._run(tool, parameters, grant=grant, context=context)

    def execute_tool(
        self,
        tool: BaseTool,
        parameters: Mapping[str, Any],
        context: RuntimeContext | None = None,
        grant: RuntimeExecutionGrant | None = None,
    ) -> Any:
        """Verify the grant, then execute a BaseTool handle."""
        self._authorize(tool.tool_id, parameters, grant)
        return self._run(tool, parameters, grant=grant, context=context)

    def _authorize(
        self,
        tool_id: str,
        parameters: Mapping[str, Any],
        grant: RuntimeExecutionGrant | None,
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

    def _safe_emit(
        self,
        event_type: TelemetryEventType,
        tool_id: str,
        session_id: str,
        agent_id: str,
        trace_id: str | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> None:
        if self._telemetry_emitter is not None:
            try:
                self._telemetry_emitter.emit(
                    BehavioralEvent(
                        event_type=event_type,
                        session_id=session_id,
                        agent_id=agent_id,
                        trace_id=trace_id,
                        tool_id=tool_id,
                        execution_time_ms=duration_ms,
                        error_code=error_code,
                    )
                )
            except Exception:
                # Fail-silent guarantee: telemetry projection must never fail execution
                pass

    def _run(
        self,
        tool: BaseTool,
        parameters: Mapping[str, Any],
        grant: RuntimeExecutionGrant | None = None,
        context: RuntimeContext | None = None,
    ) -> Any:
        if self._evidence_store is None or grant is None:
            # Uninstrumented execution when no evidence store is configured
            try:
                return tool.execute(dict(parameters))
            except Exception as e:
                if isinstance(e, ToolExecutionError | ToolDisabledError):
                    raise
                raise ToolExecutionError(tool.tool_id, str(e), cause=e) from e

        # N3-1: Receipt identity derived exclusively from validated grant and context
        binding_hash = hashlib.sha256(
            grant.binding.canonical_json().encode("utf-8")
        ).hexdigest()
        session_id = (
            context.session_id if (context and context.session_id) else "unspecified"
        )
        agent_id = (
            context.authenticated_agent
            if (context and context.authenticated_agent)
            else "unspecified"
        )
        trace_id = context.request_id if context else None
        receipt_id = f"rcpt-{uuid4()}"

        start_utc = datetime.now(timezone.utc)
        start_monotonic = self._monotonic_clock()

        # N3-3: Record STARTED before invoking tool. If store fails, fail closed (tool is NOT executed).
        self._evidence_store.record_started(
            receipt_id=receipt_id,
            grant_id=grant.grant_id,
            session_id=session_id,
            agent_id=agent_id,
            tool_id=tool.tool_id,
            binding_hash=binding_hash,
            started_at=start_utc,
            monotonic_start=start_monotonic,
        )

        # N3-6: Operational telemetry projection (fails silent)
        self._safe_emit(
            TelemetryEventType.EXECUTION_STARTED,
            tool_id=tool.tool_id,
            session_id=session_id,
            agent_id=agent_id,
            trace_id=trace_id,
        )

        try:
            result = tool.execute(dict(parameters))
            duration_ms = int((self._monotonic_clock() - start_monotonic) * 1000)
            completed_utc = datetime.now(timezone.utc)
            output_digest = compute_output_digest(result)

            self._evidence_store.record_terminal(
                receipt_id=receipt_id,
                status=ExecutionStatus.SUCCEEDED,
                completed_at=completed_utc,
                duration_ms=duration_ms,
                output_digest=output_digest,
            )
            self._safe_emit(
                TelemetryEventType.EXECUTION_COMPLETED,
                tool_id=tool.tool_id,
                session_id=session_id,
                agent_id=agent_id,
                trace_id=trace_id,
                duration_ms=duration_ms,
            )
            return result
        except Exception as exc:
            duration_ms = int((self._monotonic_clock() - start_monotonic) * 1000)
            completed_utc = datetime.now(timezone.utc)
            error_type = type(exc).__name__
            if isinstance(exc, TimeoutError):
                status = ExecutionStatus.TIMEOUT
                error_code = "EXECUTION_TIMEOUT"
            elif isinstance(exc, InterruptedError):
                status = ExecutionStatus.INTERRUPTED
                error_code = "EXECUTION_INTERRUPTED"
            else:
                status = ExecutionStatus.FAILED
                error_code = "TOOL_EXECUTION_ERROR"

            # N3-7: Diagnostic safety: raw exception message excluded from evidence record
            self._evidence_store.record_terminal(
                receipt_id=receipt_id,
                status=status,
                completed_at=completed_utc,
                duration_ms=duration_ms,
                error_type=error_type,
                error_code=error_code,
            )
            self._safe_emit(
                TelemetryEventType.EXECUTION_FAILED,
                tool_id=tool.tool_id,
                session_id=session_id,
                agent_id=agent_id,
                trace_id=trace_id,
                duration_ms=duration_ms,
                error_code=error_code,
            )

            if isinstance(exc, ToolExecutionError | ToolDisabledError):
                raise
            raise ToolExecutionError(tool.tool_id, str(exc), cause=exc) from exc
