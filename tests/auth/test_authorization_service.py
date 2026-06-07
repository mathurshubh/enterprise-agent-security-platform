import pytest

from app.auth.authorization_service import AuthorizationService
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import Decision
from app.models.tool import Tool, ToolRiskLevel
from app.services.agent_service import AgentService
from app.services.tool_service import ToolService


def create_agent(
    approved_tools: list[str],
) -> Agent:
    return Agent(
        agent_id="soc-agent",
        name="SOC Agent",
        owner="security-team",
        risk_tier=RiskTier.HIGH,
        approved_tools=approved_tools,
        status=AgentStatus.ACTIVE,
    )


def create_tool(
    tool_id: str,
    approval_required: bool = False,
) -> Tool:
    return Tool(
        tool_id=tool_id,
        risk_level=ToolRiskLevel.LOW,
        required_permission="files:read",
        approval_required=approval_required,
    )


def test_allow_authorized_tool():
    agent_service = AgentService()
    tool_service = ToolService()

    agent_service.register_agent(
        create_agent(["file_read"])
    )

    tool_service.register_tool(
        create_tool("file_read")
    )

    service = AuthorizationService(
        agent_service,
        tool_service,
    )

    decision = service.authorize(
        "soc-agent",
        "file_read",
    )

    assert decision == Decision.ALLOW


def test_deny_unapproved_tool():
    agent_service = AgentService()
    tool_service = ToolService()

    agent_service.register_agent(
        create_agent(["file_read"])
    )

    tool_service.register_tool(
        create_tool("shell_execute")
    )

    service = AuthorizationService(
        agent_service,
        tool_service,
    )

    decision = service.authorize(
        "soc-agent",
        "shell_execute",
    )

    assert decision == Decision.DENY


def test_approval_required():
    agent_service = AgentService()
    tool_service = ToolService()

    agent_service.register_agent(
        create_agent(["shell_execute"])
    )

    tool_service.register_tool(
        create_tool(
            "shell_execute",
            approval_required=True,
        )
    )

    service = AuthorizationService(
        agent_service,
        tool_service,
    )

    decision = service.authorize(
        "soc-agent",
        "shell_execute",
    )

    assert decision == Decision.APPROVAL_REQUIRED


def test_deny_unknown_agent():
    agent_service = AgentService()
    tool_service = ToolService()

    tool_service.register_tool(
        create_tool("file_read")
    )

    service = AuthorizationService(
        agent_service,
        tool_service,
    )

    decision = service.authorize(
        "missing-agent",
        "file_read",
    )

    assert decision == Decision.DENY


def test_deny_unknown_tool():
    agent_service = AgentService()
    tool_service = ToolService()

    agent_service.register_agent(
        create_agent(["file_read"])
    )

    service = AuthorizationService(
        agent_service,
        tool_service,
    )

    decision = service.authorize(
        "soc-agent",
        "missing-tool",
    )

    assert decision == Decision.DENY