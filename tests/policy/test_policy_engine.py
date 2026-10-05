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

# --- Lifecycle execution gate (F-09.A, ADR-024 amendment A.4) --------------------------
#
# The gate is an allow-list: execution is permitted by the presence of the executable
# state, never inferred from the absence of a deny condition. These tests exist because
# the suite previously could not tell the two apart -- swapping the deny-list for an
# allow-list broke none of its 1,668 tests, since nothing asserted that a REGISTERED
# agent could execute and nothing asserted it could not. The invariant was untested in
# both directions, which is how REGISTERED came to be executable by omission.
#
# They therefore cover the whole state space rather than today's reachable subset.


@pytest.mark.security_invariant
@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (AgentStatus.REGISTERED, LifecycleRefusalCode.AGENT_NOT_ACTIVE),
        (AgentStatus.DISABLED, LifecycleRefusalCode.AGENT_DISABLED),
        (AgentStatus.SUSPENDED, LifecycleRefusalCode.AGENT_SUSPENDED),
    ],
)
def test_only_active_may_execute_and_each_refusal_carries_its_code(
    status: AgentStatus, expected_code: LifecycleRefusalCode
) -> None:
    """Every non-executable lifecycle state is denied, with its own stable code.

    The code is asserted rather than the message, because ADR-024 A.4 makes the code the
    contract and the prose explicitly not one. A test that matched on the reason text
    would pin wording and still not pin the decision.
    """
    engine = PolicyEngine()

    result = engine.evaluate_policy(create_agent(status=status), create_tool())

    assert result.decision == Decision.DENY
    assert result.status_check.status == AuthorizationCheckStatus.FAILED
    assert result.status_check.code == expected_code.value


@pytest.mark.security_invariant
def test_active_is_permitted_and_carries_no_refusal_code() -> None:
    """The positive half. Without it, denying everything would pass the tests above."""
    engine = PolicyEngine()

    result = engine.evaluate_policy(create_agent(status=AgentStatus.ACTIVE), create_tool())

    assert result.decision == Decision.ALLOW
    assert result.status_check.status == AuthorizationCheckStatus.PASSED
    assert result.status_check.code is None


@pytest.mark.security_invariant
def test_an_unknown_lifecycle_state_is_not_executable() -> None:
    """A state nobody classified must be non-executable (ADR-024 A.4).

    This is the property the deny-list could not express: it denied an enumerated set, so
    anything outside that set -- including a state added years later by someone who never
    read the policy engine -- was executable by default. Constructed through
    ``model_construct`` to bypass enum validation, which is the only way to present the
    gate with a state the enum does not contain.

    Asserting the decision *and* that it does not raise: a gate that crashes on an unknown
    state is not fail-closed, it is merely unavailable, and the two are different outcomes
    for the caller.
    """
    engine = PolicyEngine()
    agent = create_agent().model_construct(
        agent_id="agent-unknown",
        name="Test Agent",
        owner="security-team",
        risk_tier=RiskTier.HIGH,
        approved_tools=["file_read"],
        status="QUARANTINED",  # type: ignore[arg-type]
    )

    result = engine.evaluate_policy(agent, create_tool())

    assert result.decision == Decision.DENY
    assert result.status_check.status == AuthorizationCheckStatus.FAILED
    # No classification exists, so the code says only what was established.
    assert result.status_check.code == LifecycleRefusalCode.AGENT_NOT_ACTIVE.value


@pytest.mark.security_invariant
def test_every_lifecycle_state_is_classified_as_executable_or_not() -> None:
    """No member of AgentStatus may be left unconsidered by the gate.

    Guards the omission itself rather than any one state: a state added to the enum
    without a decision here fails this test, instead of silently inheriting whichever
    default the gate happens to have.
    """
    engine = PolicyEngine()

    executable = {
        s for s in AgentStatus
        if engine.evaluate_policy(create_agent(status=s), create_tool()).decision
        != Decision.DENY
    }

    assert executable == {AgentStatus.ACTIVE}
