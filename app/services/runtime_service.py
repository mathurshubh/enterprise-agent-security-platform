import time
import uuid
from typing import Any

from app.auth.authorization_service import AuthorizationService
from app.detection.context import DetectionContext
from app.detection.engine import DetectionEngine
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import AuditEvent, Decision
from app.models.execution_binding import (
    ExecutionBinding,
    ExecutionBindingValidationError,
)
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
from app.registry.tool_registry import ToolRegistry
from app.runtime.execution_authority import ExecutionAuthority
from app.services.agent_service import AgentService
from app.services.audit_service import AuditService
from app.services.detection_service import DetectionService
from app.services.findings_service import FindingsService
from app.services.response_service import ResponseService
from app.services.risk_service import RiskService
from app.services.session_service import SessionService
from app.services.tool_service import ToolService
from app.telemetry.contracts import TelemetryEmitter


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
        findings = content_findings + session_findings

        if self._findings_service and findings:
            self._findings_service.record_findings(findings)

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

        response_action = (
            self._response_service.recommend(
                risk_assessment
            )
        )

        # Enforce Zero Trust response actions on final decision
        if recorded_event.decision == Decision.ALLOW:
            if response_action.response_type == ResponseType.SUSPEND_AGENT:
                recorded_event.decision = Decision.DENY
            elif response_action.response_type == ResponseType.REQUIRE_APPROVAL:
                recorded_event.decision = Decision.APPROVAL_REQUIRED

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
            )

        result = RuntimeResult(
            event=recorded_event,
            findings=findings,
            risk_assessment=risk_assessment,
            response_action=response_action,
            authorization=authorization,
        )
        self._last_result = result
        return result
