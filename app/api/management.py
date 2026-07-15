"""
Enterprise Management API — read-only control plane.

This router exposes registered platform state for observability and
administration.  It never invokes RuntimeService, executes tools, calls
LLM providers, evaluates authorization, or modifies runtime state.

All service instances are imported from app.api.dependencies so that this
router and the Runtime API share a single, consistent in-memory state.
"""

from fastapi import APIRouter

from app.api.dependencies import (
    agent_service,
    audit_service,
    detection_registry,
    session_service,
    tool_inventory_service,
)
from app.models.api.agent_response import AgentResponse
from app.models.api.audit_event_response import AuditEventResponse
from app.models.api.detection_rule_response import (
    DetectionRuleResponse,
    SecurityControlReferenceResponse,
)
from app.models.api.session_response import SessionResponse
from app.models.api.tool_response import ToolResponse

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
        "version": "0.9.0",
        "api_version": "v1",
        "registered_agents": len(agent_service.list_agents()),
        "registered_tools": len(tool_inventory_service.list_registered_tools()),
        "registered_detection_rules": len(detection_registry.metadata()),
        "audit_events": len(audit_service.list_events()),
    }
