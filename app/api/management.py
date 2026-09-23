"""
Enterprise Management API — observability and administrative control plane.

This router exposes registered platform state for observability and administration. It
never invokes RuntimeService, executes tools, or calls LLM providers.

It is read-only with one deliberate exception: agent reinstatement (M2b). Runtime
enforcement is one-way — the pipeline may contain an agent, and only an authorized
administrative request returns one to service — so that recovery has to enter somewhere,
and it enters here, gated on the ADMIN role and routed through EnforcementCoordinator.
That single role-gated route is not management-plane RBAC; the rest of this API still
enforces authentication only (finding H-2).

All service instances are imported from app.api.dependencies so that this
router and the Runtime API share a single, consistent in-memory state.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import get_current_principal, require_roles
from app.api.dependencies import (
    agent_service,
    audit_service,
    detection_registry,
    enforcement_coordinator,
    findings_service,
    risk_service,
    session_service,
    tool_inventory_service,
)
from app.detection.security_standard import SecurityFramework
from app.models.api.agent_response import AgentResponse
from app.models.api.audit_event_response import AuditEventResponse
from app.models.api.detection_rule_response import (
    DetectionRuleResponse,
    SecurityControlReferenceResponse,
)
from app.models.api.enforcement_response import (
    EnforcementStateResponse,
    EnforcementTransitionResponse,
)
from app.models.api.finding_response import FindingResponse
from app.models.api.reinstate_request import ReinstateRequest
from app.models.api.risk_assessment_response import RiskAssessmentResponse
from app.models.api.session_response import SessionResponse
from app.models.api.tool_response import ToolResponse
from app.models.finding import Finding, FindingCategory, FindingStatus, Severity
from app.models.jwt_claims import JWTClaims, Role
from app.models.risk_assessment import RiskAssessment, RiskLevel
from app.services.agent_service import AgentNotFoundError, AgentNotSuspendedError
from app.services.enforcement_coordinator import ReinstatementIncompleteError
from app.services.risk_service import AmbiguousAssessmentScopeError
from app.version import get_platform_version

router = APIRouter(tags=["Management"])


# ── Agents ───────────────────────────────────────────────────────────────────


@router.get(
    "/agents",
    response_model=list[AgentResponse],
    summary="List registered agents",
)
def list_agents() -> list[AgentResponse]:
    """Return all agents registered in the platform."""
    return [
        AgentResponse(
            agent_id=agent.agent_id,
            name=agent.name,
            owner=agent.owner,
            risk_tier=agent.risk_tier.value,
            status=agent.status.value,
            approved_tools=agent.approved_tools,
        )
        for agent in agent_service.list_agents()
    ]


@router.get(
    "/agents/{agent_id}/enforcement",
    response_model=EnforcementStateResponse,
    summary="Get an agent's enforcement state and history",
)
def get_agent_enforcement(agent_id: str) -> EnforcementStateResponse:
    """Return current containment state and how the agent reached it.

    Read-only governance visibility. Enforcement transitions are a different kind of
    record from ``AuditEvent``, which describes tool decisions, so they are exposed
    here rather than folded into the audit trail.
    """
    try:
        agent = agent_service.get_agent(agent_id)
    except AgentNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        ) from err

    state = agent_service.get_enforcement_state(agent_id)

    return EnforcementStateResponse(
        agent_id=agent_id,
        status=agent.status.value,
        suspended_at=state.suspended_at,
        suspension_reason=state.suspension_reason,
        enforcement_baseline_at=state.enforcement_baseline_at,
        last_transition_at=state.last_transition_at,
        transitions=[
            EnforcementTransitionResponse(
                transition_id=transition.transition_id,
                agent_id=transition.agent_id,
                action=transition.action.value,
                actor=transition.actor,
                reason=transition.reason,
                previous_status=transition.previous_status.value,
                new_status=transition.new_status.value,
                occurred_at=transition.occurred_at,
                trigger_session_id=(
                    transition.trigger.session_id if transition.trigger else None
                ),
                trigger_risk_level=(
                    transition.trigger.risk_level.value
                    if transition.trigger and transition.trigger.risk_level
                    else None
                ),
                trigger_risk_score=(
                    transition.trigger.risk_score if transition.trigger else None
                ),
                trigger_finding_ids=list(
                    transition.trigger.finding_ids if transition.trigger else ()
                ),
            )
            for transition in agent_service.list_transitions(agent_id)
        ],
    )


@router.post(
    "/agents/{agent_id}/reinstate",
    response_model=AgentResponse,
    summary="Return a contained agent to service",
    dependencies=[Depends(require_roles(Role.ADMIN))],
)
def reinstate_agent(
    agent_id: str,
    request: ReinstateRequest,
    principal: JWTClaims = Depends(get_current_principal),
) -> AgentResponse:
    """Reinstate a suspended agent (M2b).

    Runtime enforcement is one-way: the pipeline may contain an agent, and only this
    authorized administrative workflow returns one to service. The acting principal is
    taken from the token, and the reason is required, so every recovery is attributable.

    Authorization is evaluated before the agent is looked up, so an unauthorized caller
    cannot use this route to learn which agent identifiers exist.
    """
    try:
        agent = enforcement_coordinator.reinstate(
            agent_id,
            actor=principal.sub,
            reason=request.reason,
        )
    except AgentNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        ) from err
    except AgentNotSuspendedError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent '{agent_id}' is not suspended",
        ) from err
    except ReinstatementIncompleteError as err:
        # Fail-closed and repairable: the agent is active but still cannot execute.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(err),
        ) from err

    return AgentResponse(
        agent_id=agent.agent_id,
        name=agent.name,
        owner=agent.owner,
        risk_tier=agent.risk_tier.value,
        status=agent.status.value,
        approved_tools=agent.approved_tools,
    )


# ── Tools ────────────────────────────────────────────────────────────────────


@router.get(
    "/tools",
    response_model=list[ToolResponse],
    summary="List registered tools",
)
def list_tools() -> list[ToolResponse]:
    """Return metadata for all tools registered in the Tool Registry.

    Executable tool objects are never exposed through this endpoint (ADR-005).
    """
    return [
        ToolResponse(
            tool_id=tool.identity.tool_id,
            name=tool.identity.name,
            description=tool.identity.description,
            version=tool.identity.version,
        )
        for tool in tool_inventory_service.list_registered_tools()
    ]


# ── Detection rules ──────────────────────────────────────────────────────────


@router.get(
    "/detection/rules",
    response_model=list[DetectionRuleResponse],
    summary="List registered detection rules",
)
def list_detection_rules() -> list[DetectionRuleResponse]:
    """Return metadata for all detection rules active in the platform.

    This endpoint exposes the exact rule set used by RuntimeService at
    runtime, guaranteed by sharing the same DetectionRegistry instance.
    Executable rule objects are never returned.
    """
    return [
        DetectionRuleResponse(
            name=rule_metadata.name,
            category=rule_metadata.category.value,
            description=rule_metadata.description,
            controls=[
                SecurityControlReferenceResponse(
                    framework=ref.framework.value,
                    control_id=ref.control_id,
                    title=ref.title,
                    version=ref.version,
                )
                for ref in rule_metadata.controls
            ],
        )
        for rule_metadata in detection_registry.metadata()
    ]


# ── Audit events ─────────────────────────────────────────────────────────────


@router.get(
    "/audit/events",
    response_model=list[AuditEventResponse],
    summary="List audit events",
)
def list_audit_events() -> list[AuditEventResponse]:
    """Return all immutable audit events recorded by the platform."""
    return [
        AuditEventResponse(
            event_id=event.event_id,
            session_id=event.session_id,
            agent_id=event.agent_id,
            tool_id=event.tool_id,
            decision=event.decision.value,
            timestamp=event.timestamp,
        )
        for event in audit_service.list_events()
    ]


# ── Sessions ─────────────────────────────────────────────────────────────────


@router.get(
    "/sessions",
    response_model=list[SessionResponse],
    summary="List registered sessions",
)
def list_sessions() -> list[SessionResponse]:
    """Return all agent sessions registered in the platform."""
    return [
        SessionResponse(
            session_id=session.session_id,
            agent_id=session.agent_id,
            started_at=session.started_at,
        )
        for session in session_service.list_sessions()
    ]


# ── Findings ─────────────────────────────────────────────────────────────────


def _map_finding_to_response(finding: Finding) -> FindingResponse:
    mitre_techniques: list[str] = []
    for metadata in detection_registry.metadata():
        if metadata.name == finding.rule_name or metadata.name == finding.rule_id:
            for control in metadata.controls:
                if control.framework in (
                    SecurityFramework.MITRE_ATTACK,
                    SecurityFramework.MITRE_ATLAS,
                ):
                    mitre_techniques.append(control.control_id)
            break

    return FindingResponse(
        id=finding.finding_id,
        session_id=finding.session_id,
        agent_id=finding.agent_id,
        rule_id=finding.rule_id,
        rule_name=finding.rule_name,
        severity=finding.severity,
        category=finding.category,
        status=finding.status,
        description=finding.description,
        detected_at=finding.created_at,
        mitre_techniques=mitre_techniques,
    )


@router.get(
    "/findings",
    response_model=list[FindingResponse],
    summary="List security findings",
)
def list_findings(
    session_id: str | None = Query(default=None, description="Filter by session ID"),
    agent_id: str | None = Query(default=None, description="Filter by agent ID"),
    severity: Severity | None = Query(default=None, description="Filter by severity level"),
    category: FindingCategory | None = Query(default=None, description="Filter by category"),
    status: FindingStatus | None = Query(default=None, description="Filter by status"),
    rule_id: str | None = Query(default=None, description="Filter by rule ID"),
) -> list[FindingResponse]:
    """Return all security findings recorded by the platform matching optional filters."""
    findings = findings_service.list_findings(
        session_id=session_id,
        agent_id=agent_id,
        severity=severity,
        category=category,
        status=status,
        rule_id=rule_id,
    )
    return [_map_finding_to_response(f) for f in findings]


@router.get(
    "/findings/{finding_id}",
    response_model=FindingResponse,
    summary="Get security finding by ID",
)
def get_finding(finding_id: str) -> FindingResponse:
    """Return a single security finding by ID."""
    finding = findings_service.get_finding(finding_id)
    if finding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' not found",
        )
    return _map_finding_to_response(finding)


# ── Risk Assessments ─────────────────────────────────────────────────────────


def _map_risk_assessment_to_response(assessment: RiskAssessment) -> RiskAssessmentResponse:
    return RiskAssessmentResponse(
        session_id=assessment.session_id,
        agent_id=assessment.agent_id,
        risk_score=assessment.risk_score,
        risk_level=assessment.risk_level,
        finding_count=assessment.finding_count,
        assessed_at=assessment.assessed_at,
    )


@router.get(
    "/risk-assessments",
    response_model=list[RiskAssessmentResponse],
    summary="List risk assessments",
)
def list_risk_assessments(
    session_id: str | None = Query(default=None, description="Filter by session ID"),
    agent_id: str | None = Query(default=None, description="Filter by agent ID"),
    risk_level: RiskLevel | None = Query(default=None, description="Filter by risk level"),
) -> list[RiskAssessmentResponse]:
    """Return risk assessments derived from authoritative findings.

    Derived at read time; nothing is stored (ADR-027 Decision A). Existence is
    evidence-defined: the collection contains one assessment per (session, agent)
    pair that has findings, and a session that executed without producing any does
    not appear. Ordered by session_id ascending.
    """
    assessments = risk_service.reconstruct(
        findings_service.list_findings(session_id=session_id, agent_id=agent_id)
    )
    if risk_level is not None:
        # Applied after derivation: a risk level is a property of the assessment,
        # not of any single finding, so it cannot be pushed down to the evidence.
        assessments = [a for a in assessments if a.risk_level == risk_level]
    return [_map_risk_assessment_to_response(a) for a in assessments]


@router.get(
    "/risk-assessments/{session_id}",
    response_model=RiskAssessmentResponse,
    summary="Get risk assessment by session ID",
)
def get_risk_assessment(
    session_id: str,
    agent_id: str | None = Query(default=None, description="Filter by agent ID"),
) -> RiskAssessmentResponse:
    """Return the risk assessment derived from a session's authoritative findings.

    404 when the session has no evidence. That includes a session that executed
    cleanly: assessment existence is evidence-defined rather than execution-defined
    (ADR-027 Decision A).
    """
    try:
        assessment = risk_service.reconstruct_for_session(
            findings_service.list_findings(session_id=session_id),
            session_id,
            agent_id=agent_id,
        )
    except AmbiguousAssessmentScopeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="agent_id is required when multiple risk assessments exist for the session",
        ) from exc

    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Risk assessment for session '{session_id}' not found",
        )
    return _map_risk_assessment_to_response(assessment)


# ── Platform info ─────────────────────────────────────────────────────────────


@router.get(
    "/info",
    summary="Platform summary",
)
def platform_info() -> dict:
    """Return a lightweight summary of registered platform resources.

    Exposes only safe, static platform metadata and integer resource counts.
    No filesystem paths, credentials, environment variables, or internal
    configuration values are included.
    """
    return {
        "platform": "Enterprise Agent Security Platform",
        "version": get_platform_version(),
        "api_version": "v1",
        "registered_agents": len(agent_service.list_agents()),
        "registered_tools": len(tool_inventory_service.list_registered_tools()),
        "registered_detection_rules": len(detection_registry.metadata()),
        "audit_events": len(audit_service.list_events()),
        "findings": len(findings_service.list_findings()),
    }
