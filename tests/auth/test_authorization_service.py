from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational

from app.models.tool import Tool
from app.models.tool_risk_level import ToolRiskLevel

from app.auth.authorization_service import AuthorizationService, Decision
from app.models.agent import Agent, AgentStatus, RiskTier
from app.policy.policy_engine import PolicyEngine
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
        metadata=ToolMetadata(
            identity=ToolIdentity(
                tool_id=tool_id,
                name=tool_id.replace("_", " ").title(),
                description="Test tool",
            ),
            governance=ToolGovernance(
                risk_level=ToolRiskLevel.LOW,
                required_permissions=[
                    "files:read"
                ],
                approval_required=approval_required,
            ),
            capability=ToolCapability(
                category="filesystem",
            ),
            operational=ToolOperational(),
        )
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
        PolicyEngine(),
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
        PolicyEngine(),
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
        Tool(
            metadata=ToolMetadata(
                identity=ToolIdentity(
                    tool_id="shell_execute",
                    name="Shell Execute",
                    description="Execute shell commands",
                ),
                governance=ToolGovernance(
                    risk_level=ToolRiskLevel.CRITICAL,
                    required_permissions=[
                        "shell:execute",
                    ],
                    approval_required=True,
                ),
                capability=ToolCapability(
                    category="system",
                    shell_access=True,
                ),
                operational=ToolOperational(),
            )
        )
    )
    

    service = AuthorizationService(
        agent_service,
        tool_service,
        PolicyEngine(),
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
        PolicyEngine(),
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
        PolicyEngine(),
    )

    decision = service.authorize(
        "soc-agent",
        "missing-tool",
    )

    assert decision == Decision.DENY

def test_deny_suspended_agent():
    agent_service = AgentService()
    tool_service = ToolService()

    agent = create_agent(["file_read"])
    agent.status = AgentStatus.SUSPENDED

    agent_service.register_agent(agent)

    tool_service.register_tool(
        create_tool("file_read")
    )

    service = AuthorizationService(
        agent_service,
        tool_service,
        PolicyEngine(),
    )

    decision = service.authorize(
        "soc-agent",
        "file_read",
    )

    assert decision == Decision.DENY


def test_deny_disabled_agent():
    agent_service = AgentService()
    tool_service = ToolService()

    agent = create_agent(["file_read"])
    agent.status = AgentStatus.DISABLED

    agent_service.register_agent(agent)

    tool_service.register_tool(
        create_tool("file_read")
    )

    service = AuthorizationService(
        agent_service,
        tool_service,
        PolicyEngine(),
    )

    decision = service.authorize(
        "soc-agent",
        "file_read",
    )

    assert decision == Decision.DENY