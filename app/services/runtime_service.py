import time
import uuid
from threading import RLock
from typing import Any

from app.auth.authorization_service import AuthorizationService
from app.detection.context import DetectionContext
from app.detection.engine import DetectionEngine
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.agent_enforcement import EnforcementTrigger
from app.models.agent_risk_posture import AgentRiskPosture, PostureState
from app.models.audit_event import AuditEvent, Decision
from app.models.authorization_result import AuthorizationCheckStatus
from app.models.execution_binding import (
    ExecutionBinding,
    ExecutionBindingValidationError,
)
from app.models.execution_capability import (
    ExecutionCapabilities,
    FilesystemCapability,
    NetworkCapability,
    ResourceLimits,
)
from app.models.finding import Finding
from app.models.response_action import ResponseType
from app.models.runtime_context import RuntimeContext
from app.models.runtime_result import RuntimeResult
from app.models.session import (
    SessionRepositoryError,
)
from app.models.session_event import (
    AggregationScope,
    HorizonQuery,
    SessionEvent,
)
from app.models.telemetry.behavioral_event import (
    BehavioralEvent,
    compute_parameter_hash,
)
from app.models.telemetry.event_taxonomy import TelemetryEventType
from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.models.watermark import BaselineWatermark
from app.registry.tool_registry import (
    ToolNotRegisteredError,
    ToolRegistry,
    ToolVersionMismatchError,
)
from app.runtime.capability_registry import InMemoryCapabilityProfileRegistry
from app.runtime.contracts import (
    CapabilityProfileRegistryProtocol,
    ExecutionEvidenceStoreProtocol,
)
from app.runtime.execution_authority import ExecutionAuthority
from app.runtime.filesystem_resource_identity import (
    FilesystemResourceIdentityError,
    FilesystemResourceIdentityResolver,
)
from app.services.agent_lock_manager import AgentLockManager
from app.services.agent_risk_aggregate import ProjectionInvariantError
from app.services.agent_service import AgentNotFoundError, AgentService
from app.services.audit_service import AuditService
from app.services.detection_service import DetectionService
from app.services.findings_service import FindingsService
from app.services.response_service import ResponseService
from app.services.risk_aggregator import RiskAggregator
from app.services.risk_service import RiskService
from app.services.session_service import SessionBindingError, SessionService
from app.services.tool_service import ToolNotFoundError, ToolService
from app.telemetry.contracts import TelemetryEmitter

# Telemetry error code for a request that named a session owned by another agent.
SESSION_BINDING_INVALID = "SESSION_BINDING_INVALID"
# Error code for a request refused because an agent's posture could not be reconciled.
POSTURE_RECONCILIATION_FAILED = "POSTURE_RECONCILIATION_FAILED"
# Error code for a request refused because the detection horizon was unavailable.
HORIZON_UNAVAILABLE = "HORIZON_UNAVAILABLE"


class IncompleteRuntimeConfigurationError(Exception):
    """Raised when a RuntimeService is constructed without a dependency enforcement needs.

    Until M5-B.5 a missing ``RiskAggregator`` selected a second, quieter enforcement
    implementation; until M5-B.6 a missing ``FindingsService`` or ``AgentService``
    derived the response from the session assessment instead of the agent's posture.
    Both were described as compatibility for partially constructed runtimes, and both
    meant the security path a request took depended on how thoroughly a caller
    populated a constructor.

    Which path enforces must be a property of the architecture. An incomplete runtime
    therefore fails to exist rather than enforcing differently (ADR-026, ADR-027).
    """


class PostureReconciliationError(Exception):
    """Raised when an agent's posture cannot be reconciled into HEALTHY state."""


class RuntimeService:
    def __init__(
        self,
        authorization_service: AuthorizationService,
        session_service: SessionService,
        detection_engine: DetectionEngine,
        detection_service: DetectionService,
        risk_service: RiskService,
        response_service: ResponseService,
        audit_service: AuditService | None = None,
        tool_registry: ToolRegistry | None = None,
        findings_service: FindingsService | None = None,
        telemetry_emitter: TelemetryEmitter | None = None,
        execution_authority: ExecutionAuthority | None = None,
        agent_service: AgentService | None = None,
        risk_aggregator: RiskAggregator | None = None,
        lock_manager: AgentLockManager | None = None,
        capability_registry: CapabilityProfileRegistryProtocol | None = None,
        evidence_store: ExecutionEvidenceStoreProtocol | None = None,
        tool_service: ToolService | None = None,
    ) -> None:
        self._authorization_service = authorization_service
        self._session_service = session_service
        self._detection_engine = detection_engine
        self._detection_service = detection_service
        self._risk_service = risk_service
        self._response_service = response_service
        self._tool_registry = tool_registry
        # Governance authority for tool enablement. The registry answers whether an
        # executable exists; whether that version is permitted to run is declared here
        # and the two can disagree, so containment reads this one.
        self._tool_service = tool_service
        self._findings_service = findings_service
        self._telemetry_emitter = telemetry_emitter
        self._execution_authority = execution_authority
        self._agent_service = agent_service
        self._capability_registry = capability_registry or self._create_default_capability_registry()
        # Held for the composition root to hand to the executor. RuntimeService does
        # not write evidence itself: the pipeline decides, the executor observes.
        self._evidence_store = evidence_store
        if (
            self._execution_authority is not None
            and getattr(self._execution_authority, "_enforcement_repository", None) is None
            and self._agent_service is not None
        ):
            self._execution_authority._enforcement_repository = (
                self._agent_service.enforcement_repository
            )
        # The security response path is a capability, not a set of optional
        # collaborators. Each dependency below participates in deriving a response
        # from the agent's enforcement posture, and a runtime missing any of them
        # previously took a different decision path instead of failing (ADR-026,
        # ADR-027). Every missing dependency is named, because a caller that omitted
        # one has usually omitted them for the same reason and should see the whole
        # requirement at once.
        missing = [
            name
            for name, dependency in (
                ("risk_aggregator", risk_aggregator),
                ("findings_service", findings_service),
                ("agent_service", agent_service),
            )
            if dependency is None
        ]
        if missing:
            named = (
                missing[0]
                if len(missing) == 1
                else f"{', '.join(missing[:-1])} and {missing[-1]}"
            )
            raise IncompleteRuntimeConfigurationError(
                f"security response path requires {named}. A runtime that cannot "
                "derive a response from the agent's enforcement posture does not run "
                "with reduced enforcement; it is not constructed."
            )
        if audit_service is None:
            raise IncompleteRuntimeConfigurationError(
                "audit_service is required to record authoritative audit evidence."
            )
        self._audit_service = audit_service
        self._risk_aggregator = risk_aggregator
        self._lock_manager = (
            lock_manager if lock_manager is not None else AgentLockManager()
        )
        self._last_result = None

    def _version_is_enabled(self, tool_id: str, version: str) -> bool:
        """Whether governance permits this concrete version to execute.

        Fails closed without a tool service: governance state is what makes a disablement
        effective, and a composition that cannot consult it cannot establish that the
        version is permitted. Refusing yields no binding and therefore no grant, which is
        the same outcome as an unresolvable implementation.
        """
        if self._tool_service is None:
            return False
        try:
            return self._tool_service.get_tool(tool_id, version).enabled
        except ToolNotFoundError:
            # Registered as executable but absent from the governance plane: nothing
            # declares it permitted, so it is not.
            return False

    def _create_default_capability_registry(self) -> InMemoryCapabilityProfileRegistry:
        """Derive a capability profile per registered tool from the tool's own workspace.

        A tool whose workspace cannot be determined gets no profile rather than a
        ``/tmp`` default. ``workspace_root`` is the boundary the sandbox confines the
        tool to, so substituting one would grant read access to a directory nobody
        chose. With no profile the tool produces no executable grant, which is the
        fail-closed outcome.
        """
        reg = InMemoryCapabilityProfileRegistry()
        if self._tool_registry:
            for tool_id in self._tool_registry.list_tool_ids():
                try:
                    desc = self._tool_registry.resolve(tool_id)
                except ToolVersionMismatchError:
                    # A profile is derived per tool_id, so a tool registered under
                    # several versions has no single workspace this derivation can
                    # speak for. It gets no profile rather than an arbitrary one,
                    # which is the same fail-closed outcome as an undeterminable
                    # workspace below: no profile, no executable grant.
                    continue
                tool_inst = desc.instance
                tool_workspace = (
                    getattr(tool_inst, "workspace", None)
                    or getattr(tool_inst, "_workspace", None)
                ) if tool_inst else None
                if not tool_workspace:
                    continue
                ws = str(tool_workspace)
                reg.register_profile(
                    ExecutionCapabilities(
                        capability_profile_id=f"profile-{tool_id}",
                        filesystem=FilesystemCapability(
                            workspace_root=ws,
                            read_only=True,
                        ),
                        network=NetworkCapability(),
                        resources=ResourceLimits(),
                    )
                )
        return reg

    @property
    def capability_registry(self) -> CapabilityProfileRegistryProtocol | None:
        return self._capability_registry

    @property
    def evidence_store(self) -> ExecutionEvidenceStoreProtocol | None:
        return self._evidence_store

    @property
    def telemetry_emitter(self) -> TelemetryEmitter | None:
        return self._telemetry_emitter

    @property
    def execution_authority(self) -> ExecutionAuthority | None:
        return self._execution_authority

    def _safe_emit(self, event: BehavioralEvent) -> None:
        if self._telemetry_emitter is not None:
            try:
                self._telemetry_emitter.emit(event)
            except Exception:
                # Fail-silent guarantee: telemetry emission must never raise into runtime
                pass

    @property
    def findings_service(self) -> FindingsService | None:
        return self._findings_service

    @property
    def tool_registry(self) -> ToolRegistry | None:
        return self._tool_registry

    @property
    def detection_engine(self) -> DetectionEngine:
        return self._detection_engine

    @property
    def detection_service(self) -> DetectionService:
        return self._detection_service

    @classmethod
    def create_default(
        cls,
        agent_id: str = "agent-1",
        telemetry_emitter: TelemetryEmitter | None = None,
        execution_authority: ExecutionAuthority | None = None,
    ) -> "RuntimeService":
        from app.api.dependencies import (
            agent_service,
            audit_service,
            detection_registry,
            findings_service,
            risk_aggregator,
            session_service,
            tool_registry,
        )
        from app.services.runtime_bootstrap import bootstrap_runtime_service

        # The shared singletons, not fresh instances: a runtime holding its own
        # evidence store or projection would diverge from the one the rest of the
        # process reads, which is the failure class M5-B.1 and M5-B.4 closed.
        return bootstrap_runtime_service(
            agent_service=agent_service,
            session_service=session_service,
            audit_service=audit_service,
            detection_registry=detection_registry,
            agent_id=agent_id,
            tool_registry=tool_registry,
            findings_service=findings_service,
            risk_aggregator=risk_aggregator,
            telemetry_emitter=telemetry_emitter,
            execution_authority=execution_authority,
        )

    @staticmethod
    def _register_default_agent(
        agent_service: AgentService,
        agent_id: str,
    ) -> None:
        agent_service.register_agent(
            Agent(
                agent_id=agent_id,
                name="Local Agent",
                owner="security-team",
                risk_tier=RiskTier.HIGH,
                approved_tools=[
                    "file_read",
                    "directory_list",
                ],
                status=AgentStatus.ACTIVE,
            )
        )

    @classmethod
    def _register_default_tools(
        cls,
        tool_service: ToolService,
    ) -> None:
        tool_service.register_tool(
            cls._create_filesystem_tool(
                tool_id="file_read",
                name="File Read",
                description="Read files from the workspace",
                required_permission="files:read",
            )
        )

        tool_service.register_tool(
            cls._create_filesystem_tool(
                tool_id="directory_list",
                name="Directory List",
                description="List files in the workspace",
                required_permission="files:list",
            )
        )

    @staticmethod
    def _create_filesystem_tool(
        tool_id: str,
        name: str,
        description: str,
        required_permission: str,
    ) -> Tool:
        return Tool(
            metadata=ToolMetadata(
                identity=ToolIdentity(
                    tool_id=tool_id,
                    name=name,
                    description=description,
                ),
                governance=ToolGovernance(
                    risk_level=ToolRiskLevel.LOW,
                    required_permissions=[
                        required_permission,
                    ],
                ),
                capability=ToolCapability(
                    category="filesystem",
                    reads_files=True,
                ),
                operational=ToolOperational(),
            )
        )

    def _refuse_session_binding(
        self,
        session_id: str,
        agent_id: str,
        tool_id: str,
        resource: str | None,
        param_hash: str | None,
        trace_id: str | None,
        principal: str | None,
        tenant_id: str | None,
        started_at: float,
    ) -> RuntimeResult:
        """Refuse a request for a session owned by another agent.

        The refusal is deliberately inert. Nothing about this request may reach the
        owner's security state, so it records no session event, runs no detection,
        creates no finding, changes no posture, triggers no enforcement and issues no
        execution grant. Only the audit record and telemetry describe the attempt, which
        is what makes it investigable.
        """
        event = SessionEvent(
            session_id=session_id,
            agent_id=agent_id,
            tool_id=tool_id,
            decision=Decision.DENY,
            # A refusal is an established outcome, not an incomplete one: the request
            # never reaches the response step, so the final decision is recorded here.
            # Leaving it None would make a refusal indistinguishable from a request
            # that failed mid-pipeline.
            final_decision=Decision.DENY,
        )

        audit_event = AuditEvent(
            event_id=f"evt-{uuid.uuid4()}",
            session_id=session_id,
            agent_id=agent_id,
            # Refused at a trust boundary, before any tool resolution: the request named
            # this tool, and nothing established that it exists or which version it meant.
            requested_tool_id=tool_id,
            decision=Decision.DENY,
        )
        self._audit_service.record_event(audit_event)

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        self._safe_emit(
            BehavioralEvent(
                event_type=TelemetryEventType.GOVERNANCE_DECISION_FINALIZED,
                session_id=session_id,
                agent_id=agent_id,
                trace_id=trace_id,
                principal=principal,
                tenant_id=tenant_id,
                tool_id=tool_id,
                resource_target=resource,
                parameter_hash=param_hash,
                decision=Decision.DENY,
                execution_time_ms=elapsed_ms,
                error_code=SESSION_BINDING_INVALID,
            )
        )

        # No assessment was performed: this request never reached detection or risk, so
        # it reports no risk and no response rather than a benign-looking LOW one.
        result = RuntimeResult(
            event=event,
            findings=[],
            risk_assessment=None,
            enforcement_posture=None,
            response_action=None,
            refusal_reason=SESSION_BINDING_INVALID,
            authorization=None,
            audit_event_id=audit_event.event_id,
        )
        self._last_result = result
        return result

    def _finalize_refused_event(self, recorded_event: SessionEvent) -> SessionEvent:
        """Record DENY as the terminal decision of an already-persisted event.

        A refusal is an established outcome, not an incomplete one. Leaving
        ``final_decision`` unset would leave the durable record saying the request was
        authorized and never concluded, which a later reader — including the detection
        horizon, which queries these rows — cannot tell apart from a request that crashed
        mid-pipeline.

        Goes through ``update_event_final_decision`` rather than writing the field
        directly, so a refusal is subject to the same finalization invariant as any other
        outcome: settable once, idempotent on repeat, and rejected if it would overwrite a
        different decision.
        """
        self._session_service.update_event_final_decision(
            session_id=recorded_event.session_id,
            sequence_number=recorded_event.sequence_number,
            final_decision=Decision.DENY,
        )
        return recorded_event.model_copy(update={"final_decision": Decision.DENY})

    def _refuse_posture_reconciliation(
        self,
        recorded_event: SessionEvent,
        resolved_tool_id: str | None,
        resource: str | None,
        param_hash: str,
        trace_id: str | None,
        principal: str | None,
        tenant_id: str | None,
        started_at: float,
        findings: list[Finding],
    ) -> RuntimeResult:
        """Fail closed when an agent's posture cannot be reconciled.

        The request is denied at the authorization/execution boundary without fabricating
        a synthetic CRITICAL risk score. This preserves the distinction between active
        risk evidence and security-state availability.

        Reached after the pipeline has already persisted the request's event, so it takes
        that event rather than building one: the persisted record is the authoritative one
        for this request, and a second object asserting a different outcome would leave two
        records of one request disagreeing.
        """
        session_id = recorded_event.session_id
        agent_id = recorded_event.agent_id
        tool_id = recorded_event.tool_id
        event = self._finalize_refused_event(recorded_event)

        audit_event = AuditEvent(
            event_id=f"evt-{uuid.uuid4()}",
            session_id=session_id,
            agent_id=agent_id,
            requested_tool_id=tool_id,
            # Resolution already happened; the refusal is downstream of it. Reporting no
            # resolved identity here would state that nothing was established about this
            # tool, which the persisted event disproves.
            tool_id=resolved_tool_id,
            tool_version=recorded_event.tool_version,
            decision=Decision.DENY,
        )
        self._audit_service.record_event(audit_event)

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        self._safe_emit(
            BehavioralEvent(
                event_type=TelemetryEventType.GOVERNANCE_DECISION_FINALIZED,
                session_id=session_id,
                agent_id=agent_id,
                trace_id=trace_id,
                principal=principal,
                tenant_id=tenant_id,
                tool_id=tool_id,
                resource_target=resource,
                parameter_hash=param_hash,
                decision=Decision.DENY,
                execution_time_ms=elapsed_ms,
                error_code=POSTURE_RECONCILIATION_FAILED,
            )
        )

        result = RuntimeResult(
            event=event,
            findings=findings,
            risk_assessment=None,
            enforcement_posture=None,
            response_action=None,
            refusal_reason=POSTURE_RECONCILIATION_FAILED,
            authorization=None,
            audit_event_id=audit_event.event_id,
        )
        self._last_result = result
        return result

    def _refuse_horizon_unavailable(
        self,
        recorded_event: SessionEvent,
        resolved_tool_id: str | None,
        resource: str | None,
        param_hash: str,
        trace_id: str | None,
        principal: str | None,
        tenant_id: str | None,
        started_at: float,
        error: Exception,
    ) -> RuntimeResult:
        """Fail closed when the authoritative detection horizon is unavailable.

        Like the posture refusal, this is reached after the request's event has been
        persisted, so it finalizes that event rather than constructing a replacement.
        """
        session_id = recorded_event.session_id
        agent_id = recorded_event.agent_id
        tool_id = recorded_event.tool_id
        event = self._finalize_refused_event(recorded_event)

        audit_event = AuditEvent(
            event_id=f"evt-{uuid.uuid4()}",
            session_id=session_id,
            agent_id=agent_id,
            requested_tool_id=tool_id,
            tool_id=resolved_tool_id,
            tool_version=recorded_event.tool_version,
            decision=Decision.DENY,
        )
        self._audit_service.record_event(audit_event)

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        self._safe_emit(
            BehavioralEvent(
                event_type=TelemetryEventType.GOVERNANCE_DECISION_FINALIZED,
                session_id=session_id,
                agent_id=agent_id,
                trace_id=trace_id,
                principal=principal,
                tenant_id=tenant_id,
                tool_id=tool_id,
                resource_target=resource,
                parameter_hash=param_hash,
                decision=Decision.DENY,
                execution_time_ms=elapsed_ms,
                error_code=HORIZON_UNAVAILABLE,
            )
        )

        result = RuntimeResult(
            event=event,
            findings=[],
            risk_assessment=None,
            enforcement_posture=None,
            response_action=None,
            refusal_reason=HORIZON_UNAVAILABLE,
            authorization=None,
            audit_event_id=audit_event.event_id,
        )
        self._last_result = result
        return result


    def _suspend_agent(
        self,
        agent_id: str,
        session_id: str,
        posture: AgentRiskPosture | None,
        findings: list,
    ) -> None:
        """Suspend an agent and withdraw its execution authority.

        Issuance is closed first: a concurrent request that already passed
        authorization must not be able to obtain a grant in the window between the
        status write and the revocation. Closing the gate and revoking outstanding
        grants happen atomically inside the authority, so after this returns the agent
        holds no usable authority and can obtain none.

        Suspension is monotonic here by construction: the runtime only ever escalates,
        and ``AgentService.suspend_agent`` is idempotent.
        """
        if self._execution_authority is not None:
            self._execution_authority.suspend_issuance(agent_id)

        trigger = EnforcementTrigger(
            session_id=session_id,
            risk_level=posture.risk_level if posture is not None else None,
            risk_score=posture.risk_score if posture is not None else None,
            finding_ids=tuple(finding.finding_id for finding in findings),
        )

        try:
            self._agent_service.suspend_agent(
                agent_id,
                reason="Runtime enforcement: risk posture requires suspension",
                trigger=trigger,
            )
        except AgentNotFoundError:
            # An unregistered agent is already denied by authorization; there is no
            # registry record to transition.
            pass

    def _posture_lock(self, agent_id: str) -> RLock:
        """Return the coordination lock for one agent."""
        return self._lock_manager.get_lock(agent_id)

    def _assess_agent_posture(self, agent_id: str) -> AgentRiskPosture:
        """Assess the agent's enforcement posture.

        ``RiskAggregator`` is the sole authority for agent enforcement posture
        (M5-B.5). There is no second implementation to fall back to, so this method
        either returns a posture the runtime may decide from or raises.

        - HEALTHY posture is returned in O(1) time without scanning FindingsService.
        - UNINITIALIZED or STALE postures trigger authoritative deterministic reconciliation
          under the per-agent coordination lock against the stored baseline watermark and
          authoritative findings.
        - If reconciliation fails, raises PostureReconciliationError to fail closed.
        """
        # A projection whose own invariants are violated describes an impossible
        # state (CI-1). It is not stale evidence to be rebuilt from — something
        # wrote a projection that cannot be true — so it is refused rather than
        # repaired, because a silent rebuild would conceal that it ever happened.
        # The aggregate reports the integrity failure; naming what that means for
        # a request belongs here.
        try:
            posture = self._risk_aggregator.get_posture(agent_id)
        except ProjectionInvariantError as exc:
            raise PostureReconciliationError(
                f"Projection integrity violated for agent '{agent_id}': {exc}"
            ) from exc

        if posture.state == PostureState.HEALTHY:
            return posture

        # Posture is UNINITIALIZED or STALE: perform authoritative reconciliation
        with self._posture_lock(agent_id):
            # Re-check under lock in case another thread reconciled it
            try:
                posture = self._risk_aggregator.get_posture(agent_id)
            except ProjectionInvariantError as exc:
                raise PostureReconciliationError(
                    f"Projection integrity violated for agent '{agent_id}': {exc}"
                ) from exc

            if posture.state == PostureState.HEALTHY:
                return posture

            # Obtain current stored baseline watermark (never call capture_baseline)
            try:
                watermark = self._agent_service.get_current_baseline(agent_id)
            except AgentNotFoundError:
                # An unregistered agent is already denied by authorization; assess
                # against an empty baseline rather than inventing one.
                watermark = BaselineWatermark(
                    agent_id=agent_id,
                    baseline_at=None,
                    baseline_evidence_sequence=0,
                )

            # Authoritative evidence scan for reconciliation
            authoritative_findings = self._findings_service.list_findings(
                agent_id=agent_id
            )

            try:
                reconciled = self._risk_aggregator.reconcile_agent(
                    agent_id=agent_id,
                    findings=authoritative_findings,
                    watermark=watermark,
                )
            except Exception as exc:
                raise PostureReconciliationError(
                    f"Failed to reconcile posture for agent '{agent_id}': {exc}"
                ) from exc

            if reconciled.state != PostureState.HEALTHY:
                raise PostureReconciliationError(
                    f"Failed to reconcile posture for agent '{agent_id}' (state={reconciled.state})"
                )

            return reconciled

    def execute(
        self,
        session_id: str,
        agent_id: str,
        tool_id: str,
        resource: str | None = None,
        user_prompt: str = "",
        model_output: str = "",
        tool_output: str = "",
        context: RuntimeContext | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> RuntimeResult:
        start_time = time.perf_counter()
        trace_id = context.request_id if context is not None else None
        principal = context.principal if context is not None else None
        tenant_id = (
            context.execution_metadata.get("tenant_id")
            if (context is not None and context.execution_metadata)
            else None
        )
        param_hash = compute_parameter_hash(parameters)

        # ADR-023: canonicalise the requested operation once. The binding is what a
        # final ALLOW decision will cover. An operation that cannot be bound
        # consistently (for example an explicit resource contradicting its path
        # parameter) is denied rather than authorized against an ambiguous target.
        #
        # The bound identity includes the tool version, and that version comes from the
        # resolved descriptor rather than from anything the caller supplied: the binding
        # must name the implementation that would actually run.
        #
        # Two failures are possible here and they refuse at different stages. Keeping
        # them apart is the point; collapsing them would make tool registration part of
        # authorization and would erase the authorization evidence for exactly the
        # requests that end up refused.
        #
        #   malformed operation  — there is no coherent target to evaluate, so there is
        #                          no meaningful authorization question. Refused here.
        #   unresolved tool      — the operation is well formed and "is this agent
        #                          permitted to use this tool" is answerable and worth
        #                          recording. Authorization evaluates; the containment
        #                          gate below refuses it, because no concrete,
        #                          version-pinned execution context exists.
        #
        # Approval of a tool_id is not the same fact as a registered executable
        # implementation of it. The first is a permission question, the second an
        # enforceability one.
        binding_error_code: str | None = None
        binding: ExecutionBinding | None = None
        operation_is_malformed = False

        # Containment resolves the concrete implementation and asks whether it may run.
        # Two authorities answer, and they are not the same one:
        #
        #   ToolRegistry   does an executable exist for this version
        #   ToolService    is this version governance-enabled
        #
        # They can disagree. `ToolDescriptor.enabled` is set to True at registration and
        # nothing syncs it, so an executable registered after a version was disabled
        # presents as enabled. Governance is authoritative, so the repository decides.
        #
        # This is also the only gate that makes a disablement effective. Authorization is
        # family-scoped and does not read enablement, and the executor's own check is
        # reached only on the executing path — a decision-only request would otherwise
        # obtain a grant for an implementation not permitted to run.
        tool_version: str | None = None
        descriptor = None
        if self._tool_registry is not None:
            try:
                descriptor = self._tool_registry.resolve(tool_id)
            except (ToolNotRegisteredError, ToolVersionMismatchError):
                descriptor = None

            if descriptor is not None and self._version_is_enabled(
                tool_id, descriptor.version
            ):
                tool_version = descriptor.version

        normalized_parameters = dict(parameters or {})
        descriptor_is_filesystem = (
            descriptor is not None
            and descriptor.metadata.capability.category == "filesystem"
        )
        is_filesystem_tool = descriptor_is_filesystem or tool_id in {
            "file_read",
            "directory_list",
        }
        has_path_target = resource is not None or "path" in normalized_parameters
        filesystem_profile_id = f"profile-{tool_id}"
        filesystem_profile_available = (
            self._capability_registry is not None
            and self._capability_registry.exists(filesystem_profile_id)
        )
        if (
            is_filesystem_tool
            and has_path_target
            and (tool_version is not None or filesystem_profile_available)
        ):
            try:
                if not filesystem_profile_available:
                    raise FilesystemResourceIdentityError(
                        "filesystem capability profile is unavailable"
                    )
                assert self._capability_registry is not None
                capabilities = self._capability_registry.resolve_profile(
                    filesystem_profile_id
                )
                if capabilities.filesystem is None:
                    raise FilesystemResourceIdentityError(
                        "filesystem capability profile has no workspace boundary"
                    )
                resolver = FilesystemResourceIdentityResolver(
                    capabilities.filesystem.workspace_root
                )
                declared_path = normalized_parameters.get("path")
                canonical_parameter = (
                    resolver.canonicalize(declared_path)
                    if declared_path is not None
                    else None
                )
                canonical_resource = (
                    resolver.canonicalize(resource)
                    if resource is not None
                    else None
                )
                if (
                    canonical_parameter is not None
                    and canonical_resource is not None
                    and canonical_parameter != canonical_resource
                ):
                    raise FilesystemResourceIdentityError(
                        "resource and path parameter identify different targets"
                    )
                canonical_target = canonical_parameter or canonical_resource
                if canonical_target is not None:
                    resource = canonical_target
                    if "path" in normalized_parameters:
                        normalized_parameters["path"] = canonical_target
            except FilesystemResourceIdentityError:
                binding_error_code = "EXECUTION_BINDING_INVALID"
                operation_is_malformed = True

        if operation_is_malformed:
            binding = None
        elif tool_version is None:
            # Unresolved implementation: authorization still evaluates below.
            binding_error_code = "EXECUTION_BINDING_INVALID"
        else:
            try:
                binding = ExecutionBinding.from_operation(
                    tool_id=tool_id,
                    tool_version=tool_version,
                    parameters=normalized_parameters,
                    resource=resource,
                )
                resource = binding.resource
            except ExecutionBindingValidationError:
                binding = None
                binding_error_code = "EXECUTION_BINDING_INVALID"
                operation_is_malformed = True

        self._safe_emit(
            BehavioralEvent(
                event_type=TelemetryEventType.TOOL_INVOCATION_REQUESTED,
                session_id=session_id,
                agent_id=agent_id,
                trace_id=trace_id,
                principal=principal,
                tenant_id=tenant_id,
                tool_id=tool_id,
                resource_target=resource,
                parameter_hash=param_hash,
                execution_time_ms=0,
            )
        )

        # M2b: a session is security-owned by exactly one agent. Ownership is settled
        # before any session state is read or written, because evidence gathered in a
        # session feeds that agent's enforcement posture: a request from another agent
        # must not be able to add denials, findings or risk to someone else's session.
        try:
            self._session_service.bind_or_validate(session_id, agent_id)
        except SessionBindingError:
            return self._refuse_session_binding(
                session_id=session_id,
                agent_id=agent_id,
                tool_id=tool_id,
                resource=resource,
                param_hash=param_hash,
                trace_id=trace_id,
                principal=principal,
                tenant_id=tenant_id,
                started_at=start_time,
            )

        authorization_result = None
        if operation_is_malformed:
            decision = Decision.DENY
        else:
            authorization_result = self._authorization_service.evaluate(
                agent_id,
                tool_id,
                resource,
            )
            decision = authorization_result.decision

        auth_elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        self._safe_emit(
            BehavioralEvent(
                event_type=TelemetryEventType.SECURITY_AUTHORIZATION_CHECKED,
                session_id=session_id,
                agent_id=agent_id,
                trace_id=trace_id,
                principal=principal,
                tenant_id=tenant_id,
                tool_id=tool_id,
                resource_target=resource,
                parameter_hash=param_hash,
                decision=decision,
                execution_time_ms=auth_elapsed_ms,
                error_code=binding_error_code,
            )
        )

        # Read authoritative enforcement context to capture epoch and baseline sequence
        enforcement_state = None
        if self._agent_service is not None:
            try:
                enforcement_state = self._agent_service.get_enforcement_state(agent_id)
            except AgentNotFoundError:
                enforcement_state = None
        context_epoch = enforcement_state.epoch if enforcement_state is not None else 0
        # HorizonQuery filters SessionEvent.agent_sequence, so it reads the watermark
        # captured in that namespace. The findings watermark lives alongside it and
        # belongs to the risk projection; the two count different things.
        baseline_agent_seq = (
            enforcement_state.baseline_agent_sequence
            if enforcement_state is not None
            else 0
        )

        if context is None:
            context = RuntimeContext(
                session_id=session_id,
                request_id=f"req-{uuid.uuid4()}",
                user_id="default-user",
                principal="default-principal",
                authenticated_agent=agent_id,
            )

        event = SessionEvent(
            session_id=session_id,
            agent_id=agent_id,
            tool_id=tool_id,
            tool_version=tool_version,
            decision=decision,
        )

        recorded_event = self._session_service.record_event(event)

        # What resolution established about the tool, computed once and read by every
        # record this request produces. A resolved version implies a resolved family —
        # containment cannot reach an implementation whose family does not exist — and
        # absent a version, authorization's own existence check determined the family.
        # Derived here rather than at each emission site so a refusal and a completion
        # cannot describe the same request differently.
        resolved_tool_id = (
            tool_id
            if tool_version is not None
            or (
                authorization_result is not None
                and authorization_result.tool_check.status
                == AuthorizationCheckStatus.PASSED
            )
            else None
        )

        # Read from the enforcement snapshot captured above, not from a second
        # timestamp-parameterised call. DR-8(c): baseline_agent_sequence and
        # recovery_generation must come from the same authoritative snapshot, so the
        # watermark and the generation cannot disagree about which recovery lifecycle
        # is in force, and no recovery generation is derived from wall-clock time.
        #
        # This supersedes an earlier read taken at the triggering event's timestamp.
        # That read existed to keep a past event's identity stable under replay, but it
        # derived the value from a clock-parameterised ledger count, so it could be
        # taken at the wrong moment. Replay stability now comes from the value being
        # allocated and then stamped immutably onto the finding: it is recorded once,
        # not recomputed. This remains a read -- the runtime may escalate enforcement
        # and can never relax it.
        recovery_generation = (
            enforcement_state.recovery_generation
            if enforcement_state is not None
            else 0
        )

        content_findings = self._detection_engine.evaluate(
            DetectionContext(
                session_id=session_id,
                agent_id=agent_id,
                user_prompt=user_prompt,
                model_output=model_output,
                tool_output=tool_output,
                # Content rules fire per request, so the triggering event is what
                # separates one occurrence of a condition from a later one.
                triggering_event_sequence=recorded_event.sequence_number,
                metadata={
                    "tool_id": tool_id,
                    "resource": resource or "",
                },
            )
        )

        # Plane 2A: Query authoritative detection horizon
        rule_descriptor = self._detection_service.get_rule_descriptor(
            "EXCESSIVE_DENIALS"
        )
        horizon_query = HorizonQuery(
            agent_id=agent_id,
            scope=rule_descriptor.scope,
            session_id=(
                session_id
                if rule_descriptor.scope == AggregationScope.SESSION
                else None
            ),
            window_seconds=rule_descriptor.horizon_seconds,
            evaluation_time=recorded_event.timestamp,
            baseline_agent_sequence=baseline_agent_seq,
        )

        try:
            eligible_events = self._session_service.list_eligible_events(
                horizon_query
            )
        except SessionRepositoryError as exc:
            return self._refuse_horizon_unavailable(
                recorded_event=recorded_event,
                resolved_tool_id=resolved_tool_id,
                resource=resource,
                param_hash=param_hash,
                trace_id=trace_id,
                principal=principal,
                tenant_id=tenant_id,
                started_at=start_time,
                error=exc,
            )

        # The moment being evaluated is the event that triggered this evaluation,
        # not the moment the code happens to run, so the same evidence yields the
        # same finding whether evaluated live or replayed later.
        session_findings = self._detection_service.detect_excessive_denials(
            eligible_events,
            evaluation_time=recorded_event.timestamp,
            prior_findings=self._findings_service.list_findings(
                session_id=session_id, agent_id=agent_id
            ),
            recovery_generation=recovery_generation,
        )

        # A threshold detection is evidence of one crossing, not of every request
        # that follows it. ``record_new_findings`` keeps the original record and
        # reports only newly recorded evidence, so a crossed threshold cannot raise
        # cumulative risk again on later requests.
        findings: list[Finding] = []
        with self._posture_lock(agent_id):
            findings = self._findings_service.record_new_findings(
                content_findings + session_findings
            )
            for f in findings:
                try:
                    self._risk_aggregator.ingest_finding(f)
                except Exception:
                    self._risk_aggregator.mark_stale(agent_id)
                    # Projection failed closed to STALE; do not roll back authoritative evidence

        # Retrieve accumulated historical findings for session + agent scope to calculate cumulative risk posture
        accumulated_findings = self._findings_service.list_findings(
            session_id=session_id,
            agent_id=agent_id,
        )

        risk_assessment = self._risk_service.assess_session(
            session_id=session_id,
            agent_id=agent_id,
            findings=accumulated_findings,
        )

        # M2b: enforcement is derived from the agent's accumulated posture, not from
        # one session's assessment, so rotating to a fresh session_id cannot present an
        # accumulated posture as new (finding H-3). The session assessment above keeps
        # its meaning for reporting and attribution.
        #
        # Both services are construction preconditions (M5-B.6), so there is no
        # partially wired runtime here to branch for: every request reaching this
        # point derives its response from the agent's enforcement posture.
        try:
            enforcement_posture = self._assess_agent_posture(agent_id)
        except PostureReconciliationError:
            return self._refuse_posture_reconciliation(
                recorded_event=recorded_event,
                resolved_tool_id=resolved_tool_id,
                resource=resource,
                param_hash=param_hash,
                trace_id=trace_id,
                principal=principal,
                tenant_id=tenant_id,
                started_at=start_time,
                findings=findings,
            )

        response_action = self._response_service.recommend_for_level(
            enforcement_posture.risk_level,
            session_id=session_id,
            agent_id=agent_id,
        )

        # The response may override what authorization concluded. That override is
        # written to `final_decision`, never back onto `decision`: detection has
        # already evaluated `decision`, and rewriting it made a later reader see a
        # different history than the one detection was given. Assigned on every
        # completed request, not only on escalation, so that None keeps its meaning.
        final_decision = recorded_event.decision
        if recorded_event.decision == Decision.ALLOW:
            if response_action.response_type == ResponseType.SUSPEND_AGENT:
                final_decision = Decision.DENY
            elif response_action.response_type == ResponseType.REQUIRE_APPROVAL:
                final_decision = Decision.APPROVAL_REQUIRED

        # ADR-023 invariant: only a final ALLOW decision may produce an execution
        # grant. ExecutionAuthority.issue enforces this as well; it additionally
        # enforces CAS validation against expected_epoch so that concurrent enforcement
        # transitions (recovery or suspension) fail closed without grant issuance.
        authorization = None
        if self._execution_authority is not None and binding is None:
            # Containment gate for an unresolved implementation. Authorization has been
            # evaluated and recorded on its own terms; what fails here is enforceability.
            # Without a concrete, version-pinned execution context there is nothing a
            # grant could authorise, so an ALLOW is refused rather than left standing as
            # "allowed, never executed", and no grant is issued. A missing executable
            # implementation therefore can never become executable authority.
            #
            # Scoped to a configured execution authority for the same reason the
            # capability-profile gate below is: where no authority exists, no grant and
            # no execution can follow from this service at all, so there is no
            # enforceability claim to refuse.
            if final_decision == Decision.ALLOW:
                final_decision = Decision.DENY
        elif self._execution_authority is not None and binding is not None:
            # ADR-032: an executable grant must carry an explicit capability binding.
            # The executor refuses a profile-less grant, but by then the pipeline has
            # already concluded ALLOW, leaving a decision that can never be enforced —
            # "allowed, never executed". Capability binding is validated here so the
            # decision and what is enforceable agree. The executor still verifies the
            # binding independently; moving validation earlier adds a gate rather than
            # replacing one.
            cap_profile_id = None
            cap_digest = None
            profile_id = f"profile-{tool_id}"
            if self._capability_registry is not None and self._capability_registry.exists(
                profile_id
            ):
                caps = self._capability_registry.resolve_profile(profile_id)
                cap_profile_id = caps.capability_profile_id
                cap_digest = caps.compute_digest()

            if cap_profile_id is None:
                # Fail closed without issuing: a tool with no capability profile has no
                # containment to execute inside.
                if final_decision == Decision.ALLOW:
                    final_decision = Decision.DENY
            else:
                authorization = self._execution_authority.issue(
                    binding,
                    final_decision,
                    agent_id=agent_id,
                    session_id=session_id,
                    expected_epoch=context_epoch,
                    capability_profile_id=cap_profile_id,
                    capability_digest=cap_digest,
                )
                if authorization is None and final_decision == Decision.ALLOW:
                    final_decision = Decision.DENY

        recorded_event.final_decision = final_decision
        self._session_service.update_event_final_decision(
            session_id=session_id,
            sequence_number=recorded_event.sequence_number,
            final_decision=final_decision,
        )

        # M2b: containment is a state transition, not a recommendation. A response of
        # SUSPEND_AGENT suspends the agent and withdraws its execution authority, so the
        # next request is denied by policy before detection or issuance is reached.
        if response_action.response_type == ResponseType.SUSPEND_AGENT:
            self._suspend_agent(
                agent_id=agent_id,
                session_id=session_id,
                posture=enforcement_posture,
                findings=findings,
            )

        # Record audit event matching the final decision
        audit_event = AuditEvent(
            event_id=f"evt-{uuid.uuid4()}",
            session_id=session_id,
            agent_id=agent_id,
            requested_tool_id=tool_id,
            # A resolved version implies a resolved family — containment cannot reach
            # an implementation whose family does not exist. Where no version resolved,
            # authorization's own existence check is what determined the family, so the
            # record reports that rather than re-deriving it. Both are read from what the
            # pipeline concluded; neither consults a service this pipeline may not hold.
            tool_id=(
                tool_id
                if tool_version is not None
                or (
                    authorization_result is not None
                    and authorization_result.tool_check.status
                    == AuthorizationCheckStatus.PASSED
                )
                else None
            ),
            tool_version=tool_version,
            decision=final_decision,
        )
        self._audit_service.record_event(audit_event)

        total_elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        self._safe_emit(
            BehavioralEvent(
                event_type=TelemetryEventType.GOVERNANCE_DECISION_FINALIZED,
                session_id=session_id,
                agent_id=agent_id,
                trace_id=trace_id,
                principal=principal,
                tenant_id=tenant_id,
                tool_id=tool_id,
                resource_target=resource,
                parameter_hash=param_hash,
                decision=final_decision,
                risk_level=risk_assessment.risk_level,
                execution_time_ms=total_elapsed_ms,
                error_code=binding_error_code,
            )
        )

        result = RuntimeResult(
            event=recorded_event,
            findings=findings,
            risk_assessment=risk_assessment,
            enforcement_posture=enforcement_posture,
            response_action=response_action,
            authorization=authorization,
            authorization_result=authorization_result,
            audit_event_id=audit_event.event_id,
        )
        self._last_result = result
        return result
