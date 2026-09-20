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
from app.models.execution_binding import (
    ExecutionBinding,
    ExecutionBindingValidationError,
)
from app.models.finding import Finding
from app.models.response_action import ResponseType
from app.models.runtime_context import RuntimeContext
from app.models.runtime_result import RuntimeResult
from app.models.session_event import SessionEvent
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
from app.registry.tool_registry import ToolRegistry
from app.runtime.execution_authority import ExecutionAuthority
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
from app.services.tool_service import ToolService
from app.telemetry.contracts import TelemetryEmitter

# Telemetry error code for a request that named a session owned by another agent.
SESSION_BINDING_INVALID = "SESSION_BINDING_INVALID"
# Error code for a request refused because an agent's posture could not be reconciled.
POSTURE_RECONCILIATION_FAILED = "POSTURE_RECONCILIATION_FAILED"


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
    ) -> None:
        self._authorization_service = authorization_service
        self._session_service = session_service
        self._detection_engine = detection_engine
        self._detection_service = detection_service
        self._risk_service = risk_service
        self._response_service = response_service
        self._audit_service = audit_service or AuditService()
        self._tool_registry = tool_registry
        self._findings_service = findings_service
        self._telemetry_emitter = telemetry_emitter
        self._execution_authority = execution_authority
        self._agent_service = agent_service
        self._risk_aggregator = risk_aggregator
        self._lock_manager = (
            lock_manager if lock_manager is not None else AgentLockManager()
        )
        self._last_result = None

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
            session_service,
            tool_registry,
        )
        from app.services.runtime_bootstrap import bootstrap_runtime_service

        return bootstrap_runtime_service(
            agent_service=agent_service,
            session_service=session_service,
            audit_service=audit_service,
            detection_registry=detection_registry,
            agent_id=agent_id,
            tool_registry=tool_registry,
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
        )

        audit_event = AuditEvent(
            event_id=f"evt-{uuid.uuid4()}",
            agent_id=agent_id,
            tool_id=tool_id,
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
        )
        self._last_result = result
        return result

    def _refuse_posture_reconciliation(
        self,
        session_id: str,
        agent_id: str,
        tool_id: str,
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
        """
        event = SessionEvent(
            session_id=session_id,
            agent_id=agent_id,
            tool_id=tool_id,
            decision=Decision.DENY,
        )

        audit_event = AuditEvent(
            event_id=f"evt-{uuid.uuid4()}",
            agent_id=agent_id,
            tool_id=tool_id,
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

        if self._agent_service is None:
            return

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

        When RiskAggregator is available (M5-B):
        - HEALTHY posture is returned in O(1) time without scanning FindingsService.
        - UNINITIALIZED or STALE postures trigger authoritative deterministic reconciliation
          under the per-agent coordination lock against the stored baseline watermark and
          authoritative findings.
        - If reconciliation fails, raises PostureReconciliationError to fail closed.

        When RiskAggregator is absent (legacy fallback):
        - Scans findings under the per-agent lock via RiskService.assess_agent.
        """
        if self._risk_aggregator is not None:
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
                if self._agent_service is not None:
                    try:
                        watermark = self._agent_service.get_current_baseline(agent_id)
                    except AgentNotFoundError:
                        watermark = BaselineWatermark(
                            agent_id=agent_id,
                            baseline_at=None,
                            baseline_sequence=0,
                        )
                else:
                    watermark = BaselineWatermark(
                        agent_id=agent_id,
                        baseline_at=None,
                        baseline_sequence=0,
                    )

                # Authoritative evidence scan for reconciliation
                authoritative_findings: list[Finding] = []
                if self._findings_service is not None:
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

        # Legacy fallback when RiskAggregator is not wired
        with self._posture_lock(agent_id):
            baseline_at = None
            if self._agent_service is not None:
                try:
                    baseline_at = self._agent_service.get_enforcement_state(
                        agent_id
                    ).enforcement_baseline_at
                except AgentNotFoundError:
                    # An unregistered agent is already denied by authorization; assess
                    # what was recorded rather than inventing a baseline.
                    baseline_at = None

            # Eligibility is a property of when the evidence store accepted a finding,
            # not of Finding.created_at, which detection rules set deterministically so
            # findings stay reproducible. Filtering here keeps RiskService responsible
            # for scoring rather than for deciding what counts as history.
            agent_findings = self._findings_service.list_findings(
                agent_id=agent_id,
                recorded_after=baseline_at,
            )

            return self._risk_service.assess_agent(
                agent_id,
                agent_findings,
                baseline_at=baseline_at,
            )

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
        binding_error_code: str | None = None
        binding: ExecutionBinding | None
        try:
            binding = ExecutionBinding.from_operation(
                tool_id=tool_id,
                parameters=parameters,
                resource=resource,
            )
            resource = binding.resource
        except ExecutionBindingValidationError:
            binding = None
            binding_error_code = "EXECUTION_BINDING_INVALID"

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

        if binding is None:
            decision = Decision.DENY
        else:
            decision = self._authorization_service.authorize(
                agent_id,
                tool_id,
                resource,
            )

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
            decision=decision,
        )

        recorded_event = self._session_service.record_event(event)
        session_events = self._session_service.list_events(session_id)

        content_findings = self._detection_engine.evaluate(
            DetectionContext(
                session_id=session_id,
                agent_id=agent_id,
                user_prompt=user_prompt,
                model_output=model_output,
                tool_output=tool_output,
                metadata={
                    "tool_id": tool_id,
                    "resource": resource or "",
                },
            )
        )
        session_findings = self._detection_service.detect_excessive_denials(
            session_events
        )

        # A threshold detection is evidence of one crossing, not of every request
        # that follows it. ``record_new_findings`` keeps the original record and
        # reports only newly recorded evidence, so a crossed threshold cannot raise
        # cumulative risk again on later requests.
        findings: list[Finding] = []
        if self._findings_service:
            with self._posture_lock(agent_id):
                findings = self._findings_service.record_new_findings(
                    content_findings + session_findings
                )
                if self._risk_aggregator is not None:
                    for f in findings:
                        try:
                            self._risk_aggregator.ingest_finding(f)
                        except Exception:
                            self._risk_aggregator.mark_stale(agent_id)
                            # Projection failed closed to STALE; do not roll back authoritative evidence
        else:
            findings = content_findings + session_findings

        # Retrieve accumulated historical findings for session + agent scope to calculate cumulative risk posture
        if self._findings_service:
            accumulated_findings = self._findings_service.list_findings(
                session_id=session_id,
                agent_id=agent_id,
            )
        else:
            accumulated_findings = findings

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
        # The fallback below is compatibility behaviour for partially constructed
        # runtimes, which exist only in tests that predate this wiring. Production
        # bootstrapping always supplies both services, so a live request never silently
        # enforces on the weaker session posture.
        enforcement_posture = None
        if self._findings_service is not None and self._agent_service is not None:
            try:
                enforcement_posture = self._assess_agent_posture(agent_id)
            except PostureReconciliationError:
                return self._refuse_posture_reconciliation(
                    session_id=session_id,
                    agent_id=agent_id,
                    tool_id=tool_id,
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
        else:
            response_action = self._response_service.recommend(risk_assessment)

        # Enforce Zero Trust response actions on final decision
        if recorded_event.decision == Decision.ALLOW:
            if response_action.response_type == ResponseType.SUSPEND_AGENT:
                recorded_event.decision = Decision.DENY
            elif response_action.response_type == ResponseType.REQUIRE_APPROVAL:
                recorded_event.decision = Decision.APPROVAL_REQUIRED

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
            agent_id=agent_id,
            tool_id=tool_id,
            decision=recorded_event.decision,
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
                decision=recorded_event.decision,
                risk_level=risk_assessment.risk_level,
                execution_time_ms=total_elapsed_ms,
                error_code=binding_error_code,
            )
        )

        # ADR-023 invariant: only a final ALLOW decision may produce an execution
        # grant. ExecutionAuthority.issue enforces this as well; it is restated here
        # so the contract is visible where the decision is finalised.
        authorization = None
        if self._execution_authority is not None and binding is not None:
            authorization = self._execution_authority.issue(
                binding,
                recorded_event.decision,
                agent_id=agent_id,
            )

        result = RuntimeResult(
            event=recorded_event,
            findings=findings,
            risk_assessment=risk_assessment,
            enforcement_posture=enforcement_posture,
            response_action=response_action,
            authorization=authorization,
        )
        self._last_result = result
        return result
