import pytest

from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import Decision
from app.models.authorization_result import (
    AuthorizationCheckStatus,
    LifecycleRefusalCode,
)
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
    lifecycle_refusal=None,
    )

    assert decision == Decision.ALLOW




def test_deny_low_risk_agent_using_critical_tool():
    engine = PolicyEngine()

    decision = engine.evaluate(
        create_agent(risk_tier=RiskTier.LOW),
        create_tool(risk_level=ToolRiskLevel.CRITICAL),
    lifecycle_refusal=None,
    )

    assert decision == Decision.DENY


def test_approval_required_for_critical_tool():
    engine = PolicyEngine()

    decision = engine.evaluate(
        create_agent(risk_tier=RiskTier.HIGH),
        create_tool(risk_level=ToolRiskLevel.CRITICAL),
    lifecycle_refusal=None,
    )

    assert decision == Decision.APPROVAL_REQUIRED


def test_allow_access_to_non_protected_resource():
    engine = PolicyEngine()

    decision = engine.evaluate(
        create_agent(),
        create_tool(),
        resource="notes.txt",
        lifecycle_refusal=None,
    )

    assert decision == Decision.ALLOW



def test_deny_access_to_protected_resource():
    engine = PolicyEngine()

    decision = engine.evaluate(
        create_agent(),
        create_tool(),
        resource="secrets.txt",
        lifecycle_refusal=None,
    )

    assert decision == Decision.DENY


def test_evaluate_policy_allow_normal_access():
    engine = PolicyEngine()
    result = engine.evaluate_policy(
        create_agent(), create_tool(), resource="notes.txt", lifecycle_refusal=None
    )

    assert result.decision == Decision.ALLOW
    assert result.status_check.status == "passed"
    assert result.risk_tier_check.status == "passed"
    assert result.resource_check.status == "passed"
    assert result.reason == "All policy checks passed"



def test_evaluate_policy_deny_low_risk_critical_tool():
    engine = PolicyEngine()
    result = engine.evaluate_policy(
        create_agent(risk_tier=RiskTier.LOW),
        create_tool(risk_level=ToolRiskLevel.CRITICAL),
        lifecycle_refusal=None,
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
        lifecycle_refusal=None,
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
        lifecycle_refusal=None,
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
    result = engine.evaluate_policy(create_agent(), create_tool(), lifecycle_refusal=None)

    with pytest.raises(ValidationError):
        result.decision = Decision.DENY

# --- Lifecycle gate, after the two-plane flip (ADR-024 A.4, ADR-030 AP.1) ---
#
# The F-09.A tests that lived here drove the gate through ``agent.status``. That is no
# longer how it works: PolicyEngine does not read the projection, and the state-space
# coverage those tests provided now lives in tests/policy/test_lifecycle_authorization.py
# against the two authoritative planes, where the conditions actually are.
#
# What belongs here is the engine's own half of the contract: it refuses exactly when it
# is told to, surfaces the code it was given, and cannot be talked out of it by a status
# field.


@pytest.mark.security_invariant
@pytest.mark.parametrize("code", list(LifecycleRefusalCode))
def test_a_supplied_refusal_denies_and_is_surfaced_verbatim(
    code: LifecycleRefusalCode,
) -> None:
    """Every refusal code denies, and reaches the caller unchanged.

    Parametrized over the whole enum rather than a sample, so a code added later is
    covered without anyone extending this test. The code is the contract (A.4), so an
    engine that denied correctly while reporting a different code would still be wrong --
    an operator acts on the code.
    """
    engine = PolicyEngine()

    result = engine.evaluate_policy(create_agent(), create_tool(), lifecycle_refusal=code)

    assert result.decision == Decision.DENY
    assert result.status_check.status == AuthorizationCheckStatus.FAILED
    assert result.status_check.code == code.value


@pytest.mark.security_invariant
def test_no_refusal_permits_and_carries_no_code() -> None:
    """The positive half. Without it, denying everything would pass the test above."""
    engine = PolicyEngine()

    result = engine.evaluate_policy(create_agent(), create_tool(), lifecycle_refusal=None)

    assert result.decision == Decision.ALLOW
    assert result.status_check.status == AuthorizationCheckStatus.PASSED
    assert result.status_check.code is None


@pytest.mark.security_invariant
@pytest.mark.parametrize("status", list(AgentStatus))
def test_the_engine_does_not_consult_agent_status(status: AgentStatus) -> None:
    """AP.1: ``Agent.status`` must not be an authorization input.

    Driven from both directions, because either alone is satisfiable by accident:

    - a refusal must hold even when the projection says ACTIVE, so a stale or
      caller-constructed projection cannot buy execution;
    - permission must hold even when the projection says DISABLED, which proves the
      engine is reading the supplied plane outcome rather than falling back to the field.

    The second direction looks alarming out of context and is the point. The projection is
    not an authority, and an engine that honoured it would be consulting a value that can
    disagree with the planes it was computed from.
    """
    engine = PolicyEngine()

    refused = engine.evaluate_policy(
        create_agent(status=status),
        create_tool(),
        lifecycle_refusal=LifecycleRefusalCode.AGENT_SUSPENDED,
    )
    assert refused.decision == Decision.DENY

    permitted = engine.evaluate_policy(
        create_agent(status=status), create_tool(), lifecycle_refusal=None
    )
    assert permitted.decision == Decision.ALLOW
