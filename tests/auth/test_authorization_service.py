from app.auth.authorization_service import AuthorizationService, Decision
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.policy.policy_engine import PolicyEngine
from tests.conftest import (
    create_test_agent_service,
    create_test_tool_service,
)


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
                required_permissions=["files:read"],
                approval_required=approval_required,
            ),
            capability=ToolCapability(
                category="filesystem",
            ),
            operational=ToolOperational(),
        )
    )


def test_allow_authorized_tool():
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()

    agent_service.register_agent(create_agent(["file_read"]))

    tool_service.register_tool(create_tool("file_read"))

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
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()

    agent_service.register_agent(create_agent(["file_read"]))

    tool_service.register_tool(create_tool("shell_execute"))

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
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()

    agent_service.register_agent(create_agent(["shell_execute"]))

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
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()

    tool_service.register_tool(create_tool("file_read"))

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
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()

    agent_service.register_agent(create_agent(["file_read"]))

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
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()

    agent = create_agent(["file_read"])
    agent.status = AgentStatus.SUSPENDED

    agent_service.register_agent(agent)

    tool_service.register_tool(create_tool("file_read"))

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
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()

    agent = create_agent(["file_read"])
    agent.status = AgentStatus.DISABLED

    agent_service.register_agent(agent)

    tool_service.register_tool(create_tool("file_read"))

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


def test_evaluate_allow_authorized_tool_structured_evidence():
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()
    agent_service.register_agent(create_agent(["file_read"]))
    tool_service.register_tool(create_tool("file_read"))

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())
    result = service.evaluate("soc-agent", "file_read", resource="workspace/data.txt")

    assert result.decision == Decision.ALLOW
    assert result.agent_id == "soc-agent"
    assert result.tool_id == "file_read"
    assert result.resource == "workspace/data.txt"
    assert result.agent_check.status == "passed"
    assert result.tool_check.status == "passed"
    assert result.approved_tool_check.status == "passed"
    assert result.status_check.status == "passed"
    assert result.risk_tier_check.status == "passed"
    assert result.resource_check.status == "passed"


def test_evaluate_unknown_agent_short_circuits_with_structured_evidence():
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()
    tool_service.register_tool(create_tool("file_read"))

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())
    result = service.evaluate("missing-agent", "file_read")

    assert result.decision == Decision.DENY
    assert result.agent_check.status == "failed"
    assert result.agent_check.details["agent_id"] == "missing-agent"

    for check in [
        result.tool_check,
        result.approved_tool_check,
        result.status_check,
        result.risk_tier_check,
        result.resource_check,
    ]:
        assert check.status == "not_evaluated"
        assert check.reason == "Skipped due to prior check failure"
        assert check.details["skipped_after"] == "agent_check"


def test_evaluate_unknown_tool_short_circuits_with_structured_evidence():
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()
    agent_service.register_agent(create_agent(["file_read"]))

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())
    result = service.evaluate("soc-agent", "missing-tool")

    assert result.decision == Decision.DENY
    assert result.agent_check.status == "passed"
    assert result.tool_check.status == "failed"
    assert result.tool_check.details["tool_id"] == "missing-tool"

    for check in [
        result.approved_tool_check,
        result.status_check,
        result.risk_tier_check,
        result.resource_check,
    ]:
        assert check.status == "not_evaluated"
        assert check.reason == "Skipped due to prior check failure"
        assert check.details["skipped_after"] == "tool_check"


def test_evaluate_unapproved_tool_short_circuits_with_structured_evidence():
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()
    agent_service.register_agent(create_agent(["file_read"]))
    tool_service.register_tool(create_tool("shell_execute"))

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())
    result = service.evaluate("soc-agent", "shell_execute")

    assert result.decision == Decision.DENY
    assert result.agent_check.status == "passed"
    assert result.tool_check.status == "passed"
    assert result.approved_tool_check.status == "failed"
    assert result.approved_tool_check.details["tool_id"] == "shell_execute"

    for check in [
        result.status_check,
        result.risk_tier_check,
        result.resource_check,
    ]:
        assert check.status == "not_evaluated"
        assert check.reason == "Skipped due to prior check failure"
        assert check.details["skipped_after"] == "approved_tool_check"


def test_evaluate_suspended_agent_short_circuits_with_structured_evidence():
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()
    agent = create_agent(["file_read"])
    agent.status = AgentStatus.SUSPENDED
    agent_service.register_agent(agent)
    tool_service.register_tool(create_tool("file_read"))

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())
    result = service.evaluate("soc-agent", "file_read")

    assert result.decision == Decision.DENY
    assert result.agent_check.status == "passed"
    assert result.tool_check.status == "passed"
    assert result.approved_tool_check.status == "passed"
    assert result.status_check.status == "failed"
    assert result.status_check.details["status"] == "SUSPENDED"

    for check in [
        result.risk_tier_check,
        result.resource_check,
    ]:
        assert check.status == "not_evaluated"
        assert check.reason == "Skipped due to prior check failure"
        assert check.details["skipped_after"] == "status_check"


def test_evaluate_risk_tier_mismatch_short_circuits_resource_check():
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()
    agent = create_agent(["critical_tool"])
    agent.risk_tier = RiskTier.LOW
    agent_service.register_agent(agent)

    tool = create_tool("critical_tool")
    tool.metadata.governance.risk_level = ToolRiskLevel.CRITICAL
    tool_service.register_tool(tool)

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())
    result = service.evaluate("soc-agent", "critical_tool", resource="some_resource")

    assert result.decision == Decision.DENY
    assert result.agent_check.status == "passed"
    assert result.tool_check.status == "passed"
    assert result.approved_tool_check.status == "passed"
    assert result.status_check.status == "passed"
    assert result.risk_tier_check.status == "failed"
    assert result.risk_tier_check.details["risk_tier"] == "LOW"
    assert result.risk_tier_check.details["tool_risk_level"] == "CRITICAL"

    assert result.resource_check.status == "not_evaluated"
    assert result.resource_check.details["skipped_after"] == "risk_tier_check"


def test_evaluate_protected_resource_denied_with_structured_evidence():
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()
    agent_service.register_agent(create_agent(["file_read"]))
    tool_service.register_tool(create_tool("file_read"))

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())
    result = service.evaluate("soc-agent", "file_read", resource="secrets.txt")

    assert result.decision == Decision.DENY
    assert result.agent_check.status == "passed"
    assert result.tool_check.status == "passed"
    assert result.approved_tool_check.status == "passed"
    assert result.status_check.status == "passed"
    assert result.risk_tier_check.status == "passed"
    assert result.resource_check.status == "failed"
    assert result.resource_check.details["resource"] == "secrets.txt"


def test_evaluate_critical_tool_requires_approval_without_check_failure():
    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()
    agent = create_agent(["critical_tool"])
    agent.risk_tier = RiskTier.HIGH
    agent_service.register_agent(agent)

    tool = create_tool("critical_tool")
    tool.metadata.governance.risk_level = ToolRiskLevel.CRITICAL
    tool_service.register_tool(tool)

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())
    result = service.evaluate("soc-agent", "critical_tool")

    # Invariant 7: APPROVAL_REQUIRED is an authoritative decision state,
    # not represented as a failed check.
    assert result.decision == Decision.APPROVAL_REQUIRED
    assert result.agent_check.status == "passed"
    assert result.tool_check.status == "passed"
    assert result.approved_tool_check.status == "passed"
    assert result.status_check.status == "passed"
    assert result.risk_tier_check.status == "passed"
    assert result.resource_check.status == "passed"
    assert "CRITICAL" in result.reason


def test_authorization_result_and_check_immutability():
    import pytest
    from pydantic import ValidationError

    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()
    agent_service.register_agent(create_agent(["file_read"]))
    tool_service.register_tool(create_tool("file_read"))

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())
    result = service.evaluate("soc-agent", "file_read")

    # 1. Attribute mutation on top-level result raises ValidationError
    with pytest.raises(ValidationError):
        result.decision = Decision.DENY

    # 2. Attribute mutation on nested check raises ValidationError
    with pytest.raises(ValidationError):
        result.agent_check.status = "failed"

    # 3. In-place dictionary mutation on details mapping raises TypeError
    with pytest.raises(TypeError):
        result.agent_check.details["agent_id"] = "tampered"

    # 4. Producer-alias immutability: mutating producer dictionary does not leak
    from app.models.authorization_result import (
        AuthorizationCheck,
        AuthorizationCheckStatus,
    )

    producer_dict = {"original_key": "original_val"}
    check = AuthorizationCheck(
        status=AuthorizationCheckStatus.PASSED,
        reason="test",
        details=producer_dict,
    )
    producer_dict["original_key"] = "tampered_val"
    assert check.details["original_key"] == "original_val"


def test_evaluate_disabled_tool_short_circuits_with_structured_evidence():
    """Verify that an operationally disabled tool fails closed at the authorization gate."""
    from app.models.authorization_result import AuthorizationCheckStatus

    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()

    agent_service.register_agent(create_agent(["file_read"]))

    # Tool is registered but disabled in operational configuration
    disabled_tool = Tool(
        metadata=ToolMetadata(
            identity=ToolIdentity(
                tool_id="file_read",
                name="File Read",
                description="Read files",
            ),
            governance=ToolGovernance(
                risk_level=ToolRiskLevel.LOW,
                required_permissions=["files:read"],
                approval_required=False,
            ),
            capability=ToolCapability(
                category="filesystem",
                reads_files=True,
            ),
            operational=ToolOperational(enabled=False),
        )
    )
    tool_service.register_tool(disabled_tool)

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())

    assert service.authorize("soc-agent", "file_read") == Decision.DENY

    result = service.evaluate("soc-agent", "file_read")
    assert result.decision == Decision.DENY
    assert result.agent_check.status == AuthorizationCheckStatus.PASSED
    assert result.tool_check.status == AuthorizationCheckStatus.FAILED
    assert result.tool_check.reason == "Tool 'file_read' is disabled"
    assert result.approved_tool_check.status == AuthorizationCheckStatus.NOT_EVALUATED
    assert result.status_check.status == AuthorizationCheckStatus.NOT_EVALUATED
    assert result.risk_tier_check.status == AuthorizationCheckStatus.NOT_EVALUATED
    assert result.resource_check.status == AuthorizationCheckStatus.NOT_EVALUATED
    assert result.reason == "Tool 'file_read' is disabled"


def test_executable_registry_cannot_override_disabled_repository_state():
    """Verify that executable presence in ToolRegistry cannot override ToolRepository governance state."""
    from pathlib import Path

    from app.registry.tool_registry import ToolRegistry
    from app.repositories.in_memory.tool_repository import InMemoryToolRepository
    from app.services.tool_service import ToolService
    from app.tools.file_read_tool import FileReadTool

    agent_service = create_test_agent_service()
    tool_repo = InMemoryToolRepository()
    tool_service = ToolService(tool_repository=tool_repo)

    agent_service.register_agent(create_agent(["file_read"]))

    # Register active tool in repository, then disable it
    tool_service.register_tool(create_tool("file_read"))
    tool_service.disable_tool("file_read")
    assert tool_repo.get("file_read").enabled is False

    # ToolRegistry has an active, executable implementation
    tool_registry = ToolRegistry()
    tool_registry.register(FileReadTool(Path("demo_workspace")))
    assert tool_registry.resolve("file_read") is not None

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())

    # Authorization must fail closed based on repository governance authority
    result = service.evaluate("soc-agent", "file_read")
    assert result.decision == Decision.DENY
    assert result.reason == "Tool 'file_read' is disabled"
    assert result.tool_check.status.value == "failed"


def test_authorization_fails_closed_when_enforcement_state_unavailable():
    """Verify fail-closed DENY when dynamic enforcement state repository is unavailable."""
    from unittest.mock import MagicMock

    from app.models.authorization_result import AuthorizationCheckStatus
    from app.repositories.in_memory.agent_repository import InMemoryAgentRepository
    from app.repositories.in_memory.enforcement_state_repository import (
        InMemoryEnforcementStateRepository,
    )
    from app.services.agent_service import AgentService

    agent_repo = InMemoryAgentRepository()
    enf_repo = InMemoryEnforcementStateRepository()
    agent_service = AgentService(agent_repo, enf_repo)
    tool_service = create_test_tool_service()

    agent_service.register_agent(create_agent(["file_read"]))
    tool_service.register_tool(create_tool("file_read"))

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())

    # Simulate EnforcementStateRepository storage failure
    def broken_get_state(agent_id: str):
        raise OSError("Enforcement DB partition / storage unavailable")

    enf_repo.get_state = MagicMock(side_effect=broken_get_state)

    # 1. High-level authorize() must fail closed to DENY
    assert service.authorize("soc-agent", "file_read") == Decision.DENY

    # 2. Detailed evaluate() must return structured evidence of posture authority failure
    result = service.evaluate("soc-agent", "file_read")
    assert result.decision == Decision.DENY
    assert result.reason == "Security posture authority unavailable (fail-closed)"
    assert result.agent_check.status == AuthorizationCheckStatus.FAILED
    assert result.agent_check.reason == "Security posture authority unavailable (fail-closed)"

    # All downstream checks short-circuit to NOT_EVALUATED
    assert result.tool_check.status == AuthorizationCheckStatus.NOT_EVALUATED
    assert result.approved_tool_check.status == AuthorizationCheckStatus.NOT_EVALUATED
    assert result.status_check.status == AuthorizationCheckStatus.NOT_EVALUATED
    assert result.risk_tier_check.status == AuthorizationCheckStatus.NOT_EVALUATED
    assert result.resource_check.status == AuthorizationCheckStatus.NOT_EVALUATED


def test_authorization_succeeds_for_pristine_agent_without_dynamic_enforcement_state():
    """Verify pristine agent (None dynamic enforcement state in repo) authorizes normally."""
    from app.models.authorization_result import AuthorizationCheckStatus

    agent_service = create_test_agent_service()
    tool_service = create_test_tool_service()

    agent_service.register_agent(create_agent(["file_read"]))
    tool_service.register_tool(create_tool("file_read"))

    # Explicitly verify repository has no dynamic state for pristine agent
    assert agent_service.get_enforcement_state("soc-agent").suspended_at is None
    assert agent_service.get_enforcement_state("soc-agent").epoch == 0

    service = AuthorizationService(agent_service, tool_service, PolicyEngine())

    # Pristine agent evaluates normally
    assert service.authorize("soc-agent", "file_read") == Decision.ALLOW

    result = service.evaluate("soc-agent", "file_read")
    assert result.decision == Decision.ALLOW
    assert result.agent_check.status == AuthorizationCheckStatus.PASSED
    assert result.status_check.status == AuthorizationCheckStatus.PASSED
