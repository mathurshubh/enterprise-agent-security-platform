from app.auth.authorization_service import AuthorizationService
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import Decision
from app.models.risk_assessment import RiskLevel
from app.models.tool import Tool, ToolRiskLevel
from app.policy.policy_engine import PolicyEngine
from app.services.agent_service import AgentService
from app.services.detection_service import DetectionService
from app.services.response_service import ResponseService
from app.models.response_action import ResponseType
from app.services.risk_service import RiskService
from app.services.runtime_service import RuntimeService
from app.services.session_service import SessionService
from app.services.tool_service import ToolService


def create_runtime_service(
    approved_tools: list[str],
) -> tuple[RuntimeService, SessionService]:
    agent_service = AgentService()
    tool_service = ToolService()
    session_service = SessionService()

    agent_service.register_agent(
        Agent(
            agent_id="agent-1",
            name="Test Agent",
            owner="security-team",
            risk_tier=RiskTier.HIGH,
            approved_tools=approved_tools,
            status=AgentStatus.ACTIVE,
        )
    )
    
    tool_service.register_tool(
        Tool(
            tool_id="file_read",
            risk_level=ToolRiskLevel.LOW,
            required_permission="files:read",
        )
    )

    tool_service.register_tool(
        Tool(
            tool_id="directory_list",
            risk_level=ToolRiskLevel.LOW,
            required_permission="files:list",
        )
    )

    authorization_service = AuthorizationService(
        agent_service,
        tool_service,
        PolicyEngine(),
    )

    return (
        RuntimeService(
            authorization_service,
            session_service,
            DetectionService(),
            RiskService(),
            ResponseService(),
        ),
        session_service,
    )


def test_execute_authorized_request():
    service, session_service = create_runtime_service(
        ["file_read"]
    )

    result = service.execute(
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
    )

    assert result.event.session_id == "session-1"
    assert result.event.agent_id == "agent-1"
    assert result.event.tool_id == "file_read"
    assert result.event.decision == Decision.ALLOW
    assert result.findings == []
    assert result.risk_assessment.risk_level == RiskLevel.LOW
    assert result.risk_assessment.finding_count == 0
    assert (
        result.response_action.response_type
        == ResponseType.MONITOR
    )
    assert session_service.list_events("session-1") == [
        result.event
    ]


def test_execute_denied_request():
    service, session_service = create_runtime_service([])

    result = service.execute(
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
    )

    assert result.event.decision == Decision.DENY
    assert result.findings == []
    assert result.risk_assessment.risk_level == RiskLevel.LOW
    assert result.risk_assessment.finding_count == 0
    assert (
        result.response_action.response_type
        == ResponseType.MONITOR
    )
    assert session_service.list_events("session-1") == [
        result.event
    ]


def test_execute_detects_excessive_denials():
    service, session_service = create_runtime_service([])

    service.execute(
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
    )
    service.execute(
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
    )
    result = service.execute(
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
    )

    assert result.event.decision == Decision.DENY
    assert len(result.findings) == 1
    assert result.findings[0].rule_name == "EXCESSIVE_DENIALS"
    assert result.risk_assessment.finding_count == 1
    assert result.risk_assessment.risk_level != RiskLevel.LOW
    assert (
        result.response_action.response_type
        == ResponseType.ALERT
    )
    assert len(session_service.list_events("session-1")) == 3
