from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import Decision
from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
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
        metadata=ToolMetadata(
            identity=ToolIdentity(
                tool_id="file_read",
                name="File Read",
                description="Read files from the workspace",
            ),
            governance=ToolGovernance(
                risk_level=risk_level,
                required_permissions=[
                    "files:read",
                ],
                approval_required=False,
            ),
            capability=ToolCapability(
                category="filesystem",
                reads_files=True,
            ),
            operational=ToolOperational(),
        )
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


def test_evaluate_policy_allow_normal_access():
    engine = PolicyEngine()
    result = engine.evaluate_policy(create_agent(), create_tool(), resource="notes.txt")

    assert result.decision == Decision.ALLOW
    assert result.status_check.status == "passed"
    assert result.risk_tier_check.status == "passed"
    assert result.resource_check.status == "passed"
    assert result.reason == "All policy checks passed"


def test_evaluate_policy_deny_suspended_agent():
    engine = PolicyEngine()
    result = engine.evaluate_policy(
        create_agent(status=AgentStatus.SUSPENDED),
        create_tool(),
    )

    assert result.decision == Decision.DENY
    assert result.status_check.status == "failed"
    assert result.risk_tier_check.status == "not_evaluated"
    assert result.risk_tier_check.details["skipped_after"] == "status_check"
    assert result.resource_check.status == "not_evaluated"
    assert result.resource_check.details["skipped_after"] == "status_check"


def test_evaluate_policy_deny_low_risk_critical_tool():
    engine = PolicyEngine()
    result = engine.evaluate_policy(
        create_agent(risk_tier=RiskTier.LOW),
        create_tool(risk_level=ToolRiskLevel.CRITICAL),
    )

    assert result.decision == Decision.DENY
    assert result.status_check.status == "passed"
    assert result.risk_tier_check.status == "failed"
    assert result.resource_check.status == "not_evaluated"
    assert result.resource_check.details["skipped_after"] == "risk_tier_check"


def test_evaluate_policy_deny_protected_resource():
    engine = PolicyEngine()
    result = engine.evaluate_policy(
        create_agent(),
        create_tool(),
        resource="secrets.txt",
    )

    assert result.decision == Decision.DENY
    assert result.status_check.status == "passed"
    assert result.risk_tier_check.status == "passed"
    assert result.resource_check.status == "failed"
    assert result.resource_check.details["resource"] == "secrets.txt"


def test_evaluate_policy_approval_required_for_critical_tool():
    engine = PolicyEngine()
    result = engine.evaluate_policy(
        create_agent(risk_tier=RiskTier.HIGH),
        create_tool(risk_level=ToolRiskLevel.CRITICAL),
    )

    # All checks passed, but decision is APPROVAL_REQUIRED
    assert result.decision == Decision.APPROVAL_REQUIRED
    assert result.status_check.status == "passed"
    assert result.risk_tier_check.status == "passed"
    assert result.resource_check.status == "passed"
    assert "CRITICAL" in result.reason


def test_policy_evaluation_result_immutability():
    import pytest
    from pydantic import ValidationError

    engine = PolicyEngine()
    result = engine.evaluate_policy(create_agent(), create_tool())

    with pytest.raises(ValidationError):
        result.decision = Decision.DENY