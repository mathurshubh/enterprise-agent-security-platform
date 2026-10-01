"""ToolExecutor — Dedicated runtime component for tool instantiation, execution, and exception translation.

ADR-023 execution invariant: the executor does not trust a caller's claimed
operation. It executes only when an ``ExecutionGrant`` issued by its bound
``ExecutionAuthority`` is authentic, unexpired and unconsumed, and the requested
operation exactly matches the grant's binding. Every other case fails closed with
``ExecutionBindingError`` before the tool is instantiated or run.

ADR-032 execution isolation invariants:
- Mandatory Sandbox: Execution MUST occur within a configured ``ToolExecutionSandboxProtocol`` backend.
  If no sandbox is configured or the sandbox is unavailable, execution fails closed with ``SandboxUnavailableError``.
- Zero In-Process Fallback: The gateway process NEVER falls back to invoking ``tool.execute(...)`` in-process.
- Explicit Capability Binding: Every execution grant must carry an explicit, immutable capability binding
  (``capability_profile_id``). Missing profiles fail closed with ``CapabilityProfileNotFoundError``.
- Capability Digest Verification: The resolved capability snapshot's SHA-256 digest must match
  ``grant.capability_digest`` exactly. Discrepancies fail closed with ``CapabilityDigestMismatchError``.
- Preserved Consumption Semantics: The grant is atomically verified and consumed BEFORE dispatching to
  the sandbox (one authorized execution attempt). A subsequent execution failure does not restore the grant.
- Distinct Failure Categorization: Timeout, resource exhaustion, isolation failure, and tool failure
  are categorized distinctly in execution evidence receipts.

Execution evidence invariants (ADR-032 §12.1; these were previously cited as
"NEW-003 invariants", which named an open finding in ADR-026 rather than a document):
- N3-1 (Provenance): Execution identity is derived exclusively from the verified grant.
  ``agent_id`` and ``session_id`` are read from ``RuntimeExecutionGrant``, whose signature
  covers them, so evidence attribution never depends on a caller's claim. A supplied
  ``RuntimeContext`` contributes correlation metadata only (``request_id``), and a context
  whose identity contradicts the grant is refused as ``IDENTITY_MISMATCH`` before the grant
  is consumed.
- N3-2 (Grant/Execution Separation): Consuming a grant does not imply execution started or succeeded.
- N3-3 (Trusted Boundary): STARTED evidence established before invoking sandbox; store failure fails closed.
- N3-6 (Evidence/Telemetry Separation): Evidence store is authoritative; telemetry is operational projection.
- N3-7 (Diagnostic Safety): Raw exception messages excluded from durable evidence.
- N3-8 (Governance Independence): Execution failure does not mutate the prior ALLOW decision.
"""

import hashlib
import logging
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.models.execution_binding import (
    ExecutionBinding,
    ExecutionBindingValidationError,
)
from app.models.execution_capability import ExecutionCapabilities
from app.models.execution_provenance import ExecutionProvenance
from app.models.execution_receipt import (
    ExecutionStatus,
    compute_output_digest,
)
from app.models.runtime_context import RuntimeContext
from app.models.runtime_execution_grant import RuntimeExecutionGrant
from app.models.sandbox_execution_result import SandboxExecutionResult
from app.models.telemetry.behavioral_event import BehavioralEvent
from app.models.telemetry.event_taxonomy import TelemetryEventType
from app.models.tool_descriptor import ToolDescriptor
from app.runtime.capability_registry import verify_capability_binding
from app.runtime.contracts import (
    CapabilityProfileRegistryProtocol,
    ExecutionAuthorityProtocol,
    ExecutionEvidenceStoreProtocol,
    ToolExecutionSandboxProtocol,
    ToolRegistryProtocol,
)
from app.runtime.exceptions import (
    CapabilityProfileNotFoundError,
    ExecutionEvidenceIntegrityError,
    ExecutionEvidenceUnavailableError,
    SandboxIsolationError,
    SandboxResourceExhaustedError,
    SandboxTimeoutError,
    SandboxUnavailableError,
)
from app.runtime.execution_authority import (
    ExecutionBindingError,
    ExecutionRefusalReason,
)
from app.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Raised when an unhandled exception occurs during tool execution."""

    def __init__(
        self, tool_id: str, message: str, cause: Exception | None = None
    ) -> None:
        super().__init__(f"Execution failed for tool '{tool_id}': {message}")
        self.tool_id = tool_id
        self.cause = cause
        # Set when terminal evidence could not be recorded for a failed execution. The
        # execution failure stays primary; this carries the evidence fault alongside it
        # rather than replacing it.
        self.evidence_failure: Exception | None = None


class ToolDisabledError(Exception):
    """Raised when attempting to execute a disabled tool descriptor."""


class DefaultToolExecutor:
    """Dedicated runtime executor separating tool lookup/resolution from execution.

    Responsibilities:
    - Enforce the execution trust boundary: verify an ExecutionGrant against the
      requested operation before anything runs (ADR-023)
    - Enforce physical runtime isolation via ToolExecutionSandboxProtocol (ADR-032)
    - Verify immutable capability binding against CapabilityProfileRegistryProtocol
    - Guarantee zero in-process fallback to direct tool invocation
    - Record authoritative execution boundary evidence (ADR-032 §12)
    - Translate sandbox outcomes into structured domain exceptions and results
    """

    def __init__(
        self,
        authority: ExecutionAuthorityProtocol | None = None,
        evidence_store: ExecutionEvidenceStoreProtocol | None = None,
        telemetry_emitter: Any | None = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
        sandbox: ToolExecutionSandboxProtocol | None = None,
        capability_registry: CapabilityProfileRegistryProtocol | None = None,
        tool_registry: ToolRegistryProtocol | None = None,
    ) -> None:
        if authority is not None and not isinstance(
            authority, ExecutionAuthorityProtocol
        ):
            # Refused at wiring time rather than at execution. An authority missing part
            # of the contract used to be accepted and probed with hasattr, which turned a
            # wiring bug into silently skipped verification; surfacing it here means the
            # failure names the cause instead of raising AttributeError mid-execution.
            raise TypeError(
                "authority does not satisfy ExecutionAuthorityProtocol: the execution "
                "trust boundary requires issue, verify_grant, consume_grant and "
                "verify_and_consume"
            )

        self._authority = authority
        self._evidence_store = evidence_store
        self._telemetry_emitter = telemetry_emitter
        self._monotonic_clock = monotonic_clock
        self._sandbox = sandbox
        self._capability_registry = capability_registry
        # Used to materialise the implementation a grant names — never to choose one.
        # See ``execute``.
        self._tool_registry = tool_registry

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

    def execute(
        self,
        grant: RuntimeExecutionGrant | None,
        parameters: Mapping[str, Any],
        context: RuntimeContext | None = None,
    ) -> Any:
        """Execute the implementation a grant authorises. The production execution path.

        The grant is the sole authority for which implementation runs. Nothing here reads
        the original ``ToolInvocation``, and no caller supplies a tool: once an
        ``ExecutionGrant`` exists, an independently selected ``ToolDescriptor`` would be a
        second identity authority able to disagree with it. Comparing the two and refusing
        a mismatch would catch the disagreement, but leaving the second path expressible is
        what allows it to arise. This signature removes it.

        Resolution here is *materialisation, not selection*. The version is always taken
        from the grant's binding, so the registry is asked "give me exactly this version",
        never "which version should I use". That question was answered upstream, before
        authorization, and asking it again could answer it differently.

        Raises:
            ExecutionBindingError: no grant was supplied, or no registry is wired so the
                authorised implementation cannot be materialised.
            ToolNotRegisteredError / ToolVersionMismatchError: the exact version the grant
                names is not registered.
            ToolDisabledError: that version is registered but disabled.
        """
        if grant is None:
            # Typed as optional so this refusal is part of the contract rather than an
            # AttributeError. A pipeline reaching ALLOW without issuing a grant is a
            # wiring failure, and execution without authority is what this refuses.
            raise ExecutionBindingError(ExecutionRefusalReason.MISSING_GRANT, "")

        binding = grant.binding
        if self._tool_registry is None:
            raise ExecutionBindingError(
                ExecutionRefusalReason.NO_AUTHORITY,
                binding.tool_id,
                "executor is not bound to a tool registry and cannot materialise the "
                "implementation this grant authorises",
            )

        descriptor = self._tool_registry.resolve(
            binding.tool_id,
            # Always supplied. Omitting it would hand the version decision back to the
            # registry, which is the defect this path exists to remove.
            version=binding.tool_version,
        )
        return self._execute_resolved(descriptor, parameters, context, grant)

    def execute_descriptor(
        self,
        descriptor: ToolDescriptor,
        parameters: Mapping[str, Any],
        context: RuntimeContext | None = None,
        grant: RuntimeExecutionGrant | None = None,
    ) -> Any:
        """Internal primitive: execute a caller-supplied descriptor.

        **Not the production execution path.** Production goes through ``execute``, which
        derives the implementation from the grant. This remains for executor-internal use
        and for tests that deliberately exercise descriptor-level behaviour; a production
        caller using it reintroduces the second identity authority ``execute`` removes.

        The grant is still verified against the descriptor's own identity, so a descriptor
        disagreeing with the grant is refused rather than executed.
        """
        return self._execute_resolved(descriptor, parameters, context, grant)

    def _execute_resolved(
        self,
        descriptor: ToolDescriptor,
        parameters: Mapping[str, Any],
        context: RuntimeContext | None,
        grant: RuntimeExecutionGrant | None,
    ) -> Any:
        """Verify the grant and capability binding, then instantiate and execute via sandbox.

        A disabled tool is rejected before the grant is examined, so it cannot
        consume a grant it will never use.
        """
        if not descriptor.enabled:
            raise ToolDisabledError(f"Tool '{descriptor.tool_id}' is disabled")

        capabilities = self._verify_and_prepare(
            descriptor.tool_id, descriptor.version, parameters, grant, context
        )
        assert grant is not None
        tool = self.instantiate(descriptor)
        return self._run(
            tool,
            parameters,
            capabilities=capabilities,
            grant=grant,
            context=context,
            implementation_id=descriptor.implementation_id,
        )

    def execute_tool(
        self,
        tool: BaseTool,
        parameters: Mapping[str, Any],
        context: RuntimeContext | None = None,
        grant: RuntimeExecutionGrant | None = None,
        implementation_id: str | None = None,
    ) -> Any:
        """Internal primitive: execute a caller-supplied tool handle.

        **Not the production execution path** — see ``execute``. The implementation is
        named by the caller because there is no registration here to declare it, and it is
        never derived from the tool.
        """
        capabilities = self._verify_and_prepare(
            tool.tool_id,
            tool.metadata.identity.version,
            parameters,
            grant,
            context,
        )
        assert grant is not None
        return self._run(
            tool,
            parameters,
            capabilities=capabilities,
            grant=grant,
            implementation_id=implementation_id,
            context=context,
        )

    def _verify_and_prepare(
        self,
        tool_id: str,
        tool_version: str,
        parameters: Mapping[str, Any],
        grant: RuntimeExecutionGrant | None,
        context: RuntimeContext | None = None,
    ) -> ExecutionCapabilities:
        """Verify authority, grant, and capability binding, then consume grant before execution.

        ``tool_version`` comes from the descriptor this executor resolved, so the binding
        rebuilt here names the implementation that would actually run. A grant issued
        against a different version produces a different binding and is refused at step 3
        below — before the grant is claimed, so a substituted version cannot spend it.

        Sequence (ADR-032):
        1. Check sandbox backend is configured (fail closed if None).
        2. Verify authority is present (fail closed if None).
        3. Verify grant is present and requested operation is valid.
        3a. Refuse a caller context whose identity contradicts the verified grant.
        4. Verify explicit capability profile binding on grant (fail closed if absent).
        5. Resolve capability profile from registry (fail closed if missing).
        6. Verify capability digest matches grant.capability_digest (fail closed if mismatch).
        7. Atomically verify and claim the grant via ExecutionAuthority (fail closed if
           invalid). Claiming is one indivisible operation, not verify-then-remove.

        Returns:
            The resolved and verified immutable ExecutionCapabilities.
        """
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
                tool_version=tool_version,
                parameters=parameters,
            )
        except ExecutionBindingValidationError as exc:
            raise ExecutionBindingError(
                ExecutionRefusalReason.INVALID_REQUEST,
                tool_id,
                str(exc),
            ) from exc

        # 1. Authoritative grant verification (signature, expiry, unconsumed, binding).
        # Unconditional: an authority that cannot verify is not an authority. Probing for
        # the method left the invariant resting on the concrete class rather than on a
        # contract, so a partial double would have disabled it while tests passed.
        self._authority.verify_grant(grant, requested)

        # 1a. A caller context that contradicts the verified grant is a confused-deputy
        # signal, not something to resolve silently in the grant's favour. Refused here,
        # before consumption, so a misrouted attempt does not spend the grant.
        self._require_context_agrees_with_grant(grant, context, tool_id)

        # 2. Sandbox backend must be configured
        if self._sandbox is None:
            raise SandboxUnavailableError(
                f"No tool execution sandbox configured for tool '{tool_id}'",
                tool_id=tool_id,
            )

        # 3. ADR-032: Every sandboxed execution must have an explicit, immutable capability binding.
        profile_id = getattr(grant, "capability_profile_id", None)
        if not profile_id:
            raise CapabilityProfileNotFoundError(
                f"Grant '{grant.grant_id}' does not have an explicit capability profile binding",
                tool_id=tool_id,
            )

        if self._capability_registry is None:
            raise CapabilityProfileNotFoundError(
                f"Capability profile '{profile_id}' cannot be resolved: no capability registry configured on executor",
                tool_id=tool_id,
            )

        capabilities = self._capability_registry.resolve_profile(profile_id)
        verify_capability_binding(grant, capabilities, tool_id=tool_id)

        # 4. Claim the grant now that all pre-execution checks have passed.
        #
        # The step-1 verification above is a fast pre-check, not the gate: it releases
        # the authority lock before the capability checks run, so two callers can both
        # pass it for the same grant. claim_grant re-validates and removes the grant
        # inside a single lock hold, so exactly one caller proceeds and the rest are
        # refused as CONSUMED.
        #
        # Claiming here rather than at step 1 preserves the documented refusal
        # semantics: a capability or sandbox failure refuses without spending the grant.
        self._authority.claim_grant(grant, requested)

        return capabilities

    @staticmethod
    def _require_context_agrees_with_grant(
        grant: RuntimeExecutionGrant,
        context: RuntimeContext | None,
        tool_id: str,
    ) -> None:
        """Refuse a context whose claimed identity contradicts the verified grant.

        The grant is authoritative either way, so this changes no attribution. It exists
        because a caller presenting grant A while claiming to be subject B is either
        misrouted or attempting cross-agent execution, and both warrant a loud refusal
        rather than a silently corrected record.
        """
        if context is None:
            return

        if context.authenticated_agent and context.authenticated_agent != grant.agent_id:
            raise ExecutionBindingError(
                ExecutionRefusalReason.IDENTITY_MISMATCH,
                tool_id,
                "context agent does not match the agent the grant was issued for",
            )

        if context.session_id and context.session_id != grant.session_id:
            raise ExecutionBindingError(
                ExecutionRefusalReason.IDENTITY_MISMATCH,
                tool_id,
                "context session does not match the session the grant was issued for",
            )

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

    def _record_terminal(
        self,
        *,
        receipt_id: str,
        tool_id: str,
        session_id: str,
        agent_id: str,
        trace_id: str | None,
        status: ExecutionStatus,
        completed_at: datetime,
        duration_ms: int,
        error_type: str | None = None,
        error_code: str | None = None,
        output_digest: str | None = None,
    ) -> ExecutionEvidenceIntegrityError | None:
        """Record terminal evidence, returning an integrity error rather than raising.

        The caller decides whether the evidence fault is primary. For a successful
        execution it is: nothing else failed, and success must not be reported when the
        outcome was not established. For a failed execution it is not: the execution
        failure is the primary result and this is retained alongside it.
        """
        if self._evidence_store is None:
            return None

        try:
            self._evidence_store.record_terminal(
                receipt_id=receipt_id,
                status=status,
                completed_at=completed_at,
                duration_ms=duration_ms,
                error_type=error_type,
                error_code=error_code,
                output_digest=output_digest,
            )
            return None
        except Exception as exc:
            self._emit_evidence_failure(
                tool_id=tool_id,
                session_id=session_id,
                agent_id=agent_id,
                trace_id=trace_id,
                error_code="EVIDENCE_INTEGRITY_FAILURE",
            )
            integrity = ExecutionEvidenceIntegrityError(
                "Terminal execution evidence could not be recorded; the execution "
                "occurred and cannot be rolled back, so its outcome is not established",
                tool_id=tool_id,
                receipt_id=receipt_id,
            )
            integrity.__cause__ = exc
            return integrity

    def _emit_evidence_failure(
        self,
        *,
        tool_id: str,
        session_id: str,
        agent_id: str,
        trace_id: str | None,
        error_code: str,
    ) -> None:
        """Emit the evidence-integrity signal without the fail-silent guarantee.

        Deliberately not routed through ``_safe_emit``: that path exists so an
        observability outage cannot fail an execution, and swallowing an
        evidence-integrity event there would discard the one signal saying the platform
        cannot account for an execution that happened.

        The separation between security-state correctness and observability
        availability is still preserved. A telemetry fault is recorded locally rather
        than raised, so it never becomes an execution or evidence failure itself — but
        it is never silently dropped either.
        """
        if self._telemetry_emitter is None:
            return

        try:
            self._telemetry_emitter.emit(
                BehavioralEvent(
                    event_type=TelemetryEventType.EXECUTION_EVIDENCE_FAILED,
                    session_id=session_id,
                    agent_id=agent_id,
                    trace_id=trace_id,
                    tool_id=tool_id,
                    error_code=error_code,
                )
            )
        except Exception as exc:
            logger.error(
                "Execution evidence integrity signal could not be emitted for tool "
                "%s (%s); the evidence failure stands regardless",
                tool_id,
                type(exc).__name__,
            )

    def _run(
        self,
        tool: BaseTool,
        parameters: Mapping[str, Any],
        capabilities: ExecutionCapabilities,
        grant: RuntimeExecutionGrant,
        context: RuntimeContext | None = None,
        implementation_id: str | None = None,
    ) -> Any:
        if not implementation_id:
            # Refused before any evidence is written. The sandbox refuses this too, and
            # keeps doing so as a separate trust boundary — but a receipt is recorded
            # first, and a receipt cannot carry an identity nobody declared. Writing one
            # with a placeholder would be the inference F-05 removed, reappearing inside
            # the evidence record.
            raise ExecutionBindingError(
                ExecutionRefusalReason.NO_AUTHORITY,
                tool.tool_id,
                "no implementation is declared for this tool, so the execution has no "
                "concrete identity to record or run",
            )

        start_utc = datetime.now(timezone.utc)
        start_monotonic = self._monotonic_clock()

        # N3-1: identity is read from the verified grant, never from the context. The
        # context is unsigned caller input; it contributes request correlation only, and
        # _verify_and_prepare has already refused one that contradicts the grant.
        session_id = grant.session_id
        agent_id = grant.agent_id
        trace_id = context.request_id if context is not None else f"req-{uuid4()}"

        # Everything crossing the isolation boundary is derived from the verified grant.
        # The sandbox receives no caller-supplied context, so there is no fabricated
        # identity left to construct.
        provenance = ExecutionProvenance.from_grant(
            grant, trace_id, implementation_id=implementation_id
        )

        binding_hash = hashlib.sha256(
            grant.binding.canonical_json().encode("utf-8")
        ).hexdigest()
        receipt_id = f"rcpt-{uuid4()}"

        if self._evidence_store is not None:
            # N3-3: Record STARTED before invoking sandbox. If store fails, fail closed (sandbox is NOT executed).
            # Every identity value comes from the verified grant; request_id is
            # correlation only. declared_timeout_seconds is the limit governing THIS
            # execution, so reconciliation can derive its deadline from the capability
            # that applied rather than from a global SLA.
            try:
                self._evidence_store.record_started(
                    receipt_id=receipt_id,
                    grant_id=grant.grant_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    request_id=trace_id,
                    tool_id=tool.tool_id,
                    # An unknown outcome does not mean an unknown identity: the
                    # grant and the registration have both already answered what
                    # is about to run.
                    tool_version=grant.binding.tool_version,
                    implementation_id=implementation_id,
                    binding_hash=binding_hash,
                    capability_profile_id=grant.capability_profile_id,
                    capability_digest=grant.capability_digest,
                    declared_timeout_seconds=capabilities.resources.wall_clock_timeout_seconds,
                    started_at=start_utc,
                    monotonic_start=start_monotonic,
                )
            except Exception as exc:
                self._emit_evidence_failure(
                    tool_id=tool.tool_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    trace_id=trace_id,
                    error_code="EVIDENCE_UNAVAILABLE",
                )
                raise ExecutionEvidenceUnavailableError(
                    "STARTED execution evidence could not be recorded; execution is "
                    "refused before the sandbox is invoked",
                    tool_id=tool.tool_id,
                    receipt_id=receipt_id,
                ) from exc

        # N3-6: Operational telemetry projection (fails silent)
        self._safe_emit(
            TelemetryEventType.EXECUTION_STARTED,
            tool_id=tool.tool_id,
            session_id=session_id,
            agent_id=agent_id,
            trace_id=trace_id,
        )

        try:
            assert self._sandbox is not None
            sandbox_result: SandboxExecutionResult = self._sandbox.execute(
                tool=tool,
                parameters=parameters,
                capabilities=capabilities,
                provenance=provenance,
                # Declared at registration and carried through unchanged; the version
                # comes from the verified grant, so what runs and what the receipt
                # attributes it to are the same concrete identity.
                implementation_id=implementation_id,
                tool_version=grant.binding.tool_version,
            )
        except Exception as exc:
            duration_ms = int((self._monotonic_clock() - start_monotonic) * 1000)
            completed_utc = datetime.now(timezone.utc)
            error_type = type(exc).__name__

            if isinstance(exc, SandboxTimeoutError | TimeoutError):
                status = ExecutionStatus.TIMEOUT
                error_code = "EXECUTION_TIMEOUT"
            elif isinstance(exc, SandboxResourceExhaustedError):
                status = ExecutionStatus.FAILED
                error_code = "RESOURCE_EXHAUSTED"
            elif isinstance(exc, SandboxIsolationError | PermissionError):
                status = ExecutionStatus.FAILED
                error_code = "ISOLATION_FAILURE"
            elif isinstance(exc, InterruptedError):
                status = ExecutionStatus.INTERRUPTED
                error_code = "EXECUTION_INTERRUPTED"
            else:
                status = ExecutionStatus.FAILED
                error_code = "TOOL_EXECUTION_ERROR"

            integrity_failure = self._record_terminal(
                receipt_id=receipt_id,
                tool_id=tool.tool_id,
                session_id=session_id,
                agent_id=agent_id,
                trace_id=trace_id,
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

            # The execution failure remains primary. An evidence fault must not erase
            # the outcome it was trying to record, so it travels as secondary
            # information rather than replacing the exception the caller needs.
            if isinstance(exc, ToolExecutionError | ToolDisabledError):
                if integrity_failure is not None:
                    exc.evidence_failure = integrity_failure
                raise
            wrapped = ToolExecutionError(tool.tool_id, str(exc), cause=exc)
            wrapped.evidence_failure = integrity_failure
            raise wrapped from exc

        duration_ms = sandbox_result.duration_ms or int(
            (self._monotonic_clock() - start_monotonic) * 1000
        )
        completed_utc = datetime.now(timezone.utc)

        if sandbox_result.success:
            output_digest = sandbox_result.output_digest or compute_output_digest(
                sandbox_result.output
            )
            integrity_failure = self._record_terminal(
                receipt_id=receipt_id,
                tool_id=tool.tool_id,
                session_id=session_id,
                agent_id=agent_id,
                trace_id=trace_id,
                status=ExecutionStatus.SUCCEEDED,
                completed_at=completed_utc,
                duration_ms=duration_ms,
                output_digest=output_digest,
            )
            if integrity_failure is not None:
                # The tool succeeded, but the platform cannot establish that it did.
                # Returning the output would report an outcome no evidence supports, so
                # the evidence fault is the primary result and no COMPLETED telemetry is
                # emitted for an execution whose outcome was never recorded.
                raise integrity_failure
            self._safe_emit(
                TelemetryEventType.EXECUTION_COMPLETED,
                tool_id=tool.tool_id,
                session_id=session_id,
                agent_id=agent_id,
                trace_id=trace_id,
                duration_ms=duration_ms,
            )
            return sandbox_result.output

        # Handle sandbox_result.success is False with distinct categorization
        err_type = sandbox_result.error_type or "ToolExecutionError"
        if err_type in ("SandboxTimeoutError", "TimeoutError"):
            status = ExecutionStatus.TIMEOUT
            error_code = "EXECUTION_TIMEOUT"
        elif err_type in ("SandboxResourceExhaustedError",):
            status = ExecutionStatus.FAILED
            error_code = "RESOURCE_EXHAUSTED"
        elif err_type in ("SandboxIsolationError", "PermissionError"):
            status = ExecutionStatus.FAILED
            error_code = "ISOLATION_FAILURE"
        elif err_type in ("InterruptedError",):
            status = ExecutionStatus.INTERRUPTED
            error_code = "EXECUTION_INTERRUPTED"
        else:
            status = ExecutionStatus.FAILED
            error_code = "TOOL_EXECUTION_ERROR"

        integrity_failure = self._record_terminal(
            receipt_id=receipt_id,
            tool_id=tool.tool_id,
            session_id=session_id,
            agent_id=agent_id,
            trace_id=trace_id,
            status=status,
            completed_at=completed_utc,
            duration_ms=duration_ms,
            error_type=err_type,
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
        failure = ToolExecutionError(
            tool.tool_id,
            sandbox_result.error_message or "Tool execution failed in sandbox",
        )
        failure.evidence_failure = integrity_failure
        raise failure
