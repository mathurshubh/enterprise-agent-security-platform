from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import Decision
from app.models.tool import Tool, ToolRiskLevel
from app.policy.policy_engine import PolicyEngine


def create_agent(
    risk_tier: RiskTier = RiskTier.HIGH,
    status: AgentStatus = AgentStatus.ACTIVE,
) -> Agent:
    return Agent(
        agent_id="agent-1",
        name="Test Agent",
        owner="security-team",
        risk_tier=risk_tier,
        approved_tools=["file_read"],
        status=status,
    )


def create_tool(
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW,
) -> Tool:
    return Tool(
        tool_id="file_read",
        risk_level=risk_level,
        required_permission="files:read",
        approval_required=False,
    )


def test_allow_normal_access():
    engine = PolicyEngine()

    decision = engine.evaluate(
        create_agent(),
        create_tool(),
    )

    assert decision == Decision.ALLOW


def test_deny_suspended_agent():
    engine = PolicyEngine()

    decision = engine.evaluate(
        create_agent(status=AgentStatus.SUSPENDED),
        create_tool(),
    )

    assert decision == Decision.DENY


def test_deny_disabled_agent():
    engine = PolicyEngine()

    decision = engine.evaluate(
        create_agent(status=AgentStatus.DISABLED),
        create_tool(),
    )

    assert decision == Decision.DENY


def test_deny_low_risk_agent_using_critical_tool():
    engine = PolicyEngine()

    decision = engine.evaluate(
        create_agent(risk_tier=RiskTier.LOW),
        create_tool(risk_level=ToolRiskLevel.CRITICAL),
    )

    assert decision == Decision.DENY


def test_approval_required_for_critical_tool():
    engine = PolicyEngine()

    decision = engine.evaluate(
        create_agent(risk_tier=RiskTier.HIGH),
        create_tool(risk_level=ToolRiskLevel.CRITICAL),
    )

    assert decision == Decision.APPROVAL_REQUIRED


def test_allow_access_to_non_protected_resource():
    engine = PolicyEngine()

    decision = engine.evaluate(
        create_agent(),
        create_tool(),
        resource="notes.txt",
    )

    assert decision == Decision.ALLOW



def test_deny_access_to_protected_resource():
    engine = PolicyEngine()

    decision = engine.evaluate(
        create_agent(),
        create_tool(),
        resource="secrets.txt",
    )

    assert decision == Decision.DENY