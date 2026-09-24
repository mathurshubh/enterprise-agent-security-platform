"""Agent enforcement state: suspension, reinstatement and the monotonic boundary (M2b).

Step 1 adds state to the enforcement point that already exists — `PolicyEngine` has
always denied a suspended agent — rather than introducing a second authorization
mechanism. These tests assert the state machine and its boundary:

    REGISTERED/ACTIVE ──suspend_agent──▶ SUSPENDED ──reinstate_agent──▶ ACTIVE

No other path returns an agent to service.
"""

import inspect
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

import app.services.runtime_service as runtime_service_module
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.agent_enforcement import EnforcementAction, EnforcementTrigger
from app.models.audit_event import Decision
from app.models.risk_assessment import RiskLevel
from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.policy.policy_engine import PolicyEngine
from app.services.agent_service import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    AgentNotSuspendedError,
    AgentService,
)
from tests.conftest import create_test_agent_service

CRITICAL_TRIGGER = EnforcementTrigger(
    session_id="session-1",
    risk_level=RiskLevel.CRITICAL,
    risk_score=150,
    finding_ids=("finding-a", "finding-b"),
)


def create_agent(
    agent_id: str = "soc-agent",
    status: AgentStatus = AgentStatus.ACTIVE,
) -> Agent:
    return Agent(
        agent_id=agent_id,
        name="SOC Agent",
        owner="security-team",
        risk_tier=RiskTier.HIGH,
        approved_tools=["file_read"],
        status=status,
    )


def registered_service(status: AgentStatus = AgentStatus.ACTIVE) -> AgentService:
    service = create_test_agent_service()
    service.register_agent(create_agent(status=status))
    return service


def low_risk_tool() -> Tool:
    return Tool(
        metadata=ToolMetadata(
            identity=ToolIdentity(
                tool_id="file_read",
                name="File Read",
                description="Read files from the workspace",
            ),
            governance=ToolGovernance(
                risk_level=ToolRiskLevel.LOW,
                required_permissions=["files:read"],
            ),
            capability=ToolCapability(category="filesystem", reads_files=True),
            operational=ToolOperational(),
        )
    )


class TestSuspension:
    def test_suspension_transitions_an_active_agent(self) -> None:
        service = registered_service()

        suspended = service.suspend_agent("soc-agent", reason="critical risk posture")

        assert suspended.status == AgentStatus.SUSPENDED
        assert service.get_agent("soc-agent").status == AgentStatus.SUSPENDED

        state = service.get_enforcement_state("soc-agent")
        assert state.suspended_at is not None
        assert state.suspension_reason == "critical risk posture"

    def test_suspension_records_its_trigger(self) -> None:
        service = registered_service()

        service.suspend_agent(
            "soc-agent", reason="critical risk posture", trigger=CRITICAL_TRIGGER
        )

        transitions = service.list_transitions("soc-agent")
        assert len(transitions) == 1

        transition = transitions[0]
        assert transition.action == EnforcementAction.SUSPEND
        assert transition.actor == "runtime"
        assert transition.previous_status == AgentStatus.ACTIVE
        assert transition.new_status == AgentStatus.SUSPENDED
        assert transition.trigger == CRITICAL_TRIGGER

    def test_suspension_is_idempotent(self) -> None:
        service = registered_service()
        service.suspend_agent("soc-agent", reason="first", trigger=CRITICAL_TRIGGER)
        first_state = service.get_enforcement_state("soc-agent")

        again = service.suspend_agent("soc-agent", reason="second")

        assert again.status == AgentStatus.SUSPENDED
        assert service.get_enforcement_state("soc-agent") == first_state
        assert len(service.list_transitions("soc-agent")) == 1

    def test_suspension_leaves_a_disabled_agent_unchanged(self) -> None:
        service = registered_service(status=AgentStatus.DISABLED)

        result = service.suspend_agent("soc-agent", reason="critical risk posture")

        assert result.status == AgentStatus.DISABLED
        assert service.list_transitions("soc-agent") == []

    def test_suspension_of_unknown_agent_is_refused(self) -> None:
        with pytest.raises(AgentNotFoundError):
            create_test_agent_service().suspend_agent(
                "absent", reason="critical risk posture"
            )

    def test_registered_agent_can_be_suspended(self) -> None:
        service = registered_service(status=AgentStatus.REGISTERED)

        suspended = service.suspend_agent("soc-agent", reason="critical risk posture")

        assert suspended.status == AgentStatus.SUSPENDED

    def test_policy_engine_denies_a_suspended_agent(self) -> None:
        """Step 1 adds state to an enforcement point that already exists."""
        service = registered_service()
        policy = PolicyEngine()
        tool = low_risk_tool()

        assert policy.evaluate(service.get_agent("soc-agent"), tool) == Decision.ALLOW

        service.suspend_agent("soc-agent", reason="critical risk posture")

        assert policy.evaluate(service.get_agent("soc-agent"), tool) == Decision.DENY


class TestReinstatement:
    def test_reinstatement_returns_the_agent_to_active(self) -> None:
        service = registered_service()
        service.suspend_agent("soc-agent", reason="critical risk posture")

        reinstated = service.reinstate_agent(
            "soc-agent", actor="admin-1", reason="investigated, false positive"
        )

        assert reinstated.status == AgentStatus.ACTIVE
        assert service.get_agent("soc-agent").status == AgentStatus.ACTIVE

        transition = service.list_transitions("soc-agent")[-1]
        assert transition.action == EnforcementAction.REINSTATE
        assert transition.actor == "admin-1"
        assert transition.reason == "investigated, false positive"
        assert transition.previous_status == AgentStatus.SUSPENDED

    def test_reinstatement_sets_a_new_enforcement_baseline(self) -> None:
        service = registered_service()
        service.suspend_agent("soc-agent", reason="critical risk posture")
        assert (
            service.get_enforcement_state("soc-agent").enforcement_baseline_at is None
        )

        service.reinstate_agent("soc-agent", actor="admin-1", reason="cleared")

        state = service.get_enforcement_state("soc-agent")
        assert state.enforcement_baseline_at is not None
        assert state.suspended_at is None
        assert state.suspension_reason is None

    def test_reinstatement_requires_a_suspended_agent(self) -> None:
        service = registered_service()

        with pytest.raises(AgentNotSuspendedError):
            service.reinstate_agent("soc-agent", actor="admin-1", reason="cleared")

    @pytest.mark.parametrize(
        ("actor", "reason"), [("", "cleared"), ("admin-1", ""), ("   ", "   ")]
    )
    def test_reinstatement_must_be_attributed(self, actor: str, reason: str) -> None:
        service = registered_service()
        service.suspend_agent("soc-agent", reason="critical risk posture")

        with pytest.raises(ValueError):
            service.reinstate_agent("soc-agent", actor=actor, reason=reason)

        assert service.get_agent("soc-agent").status == AgentStatus.SUSPENDED

    def test_reinstatement_does_not_erase_history(self) -> None:
        service = registered_service()
        service.suspend_agent(
            "soc-agent", reason="critical risk posture", trigger=CRITICAL_TRIGGER
        )

        service.reinstate_agent("soc-agent", actor="admin-1", reason="cleared")

        actions = [t.action for t in service.list_transitions("soc-agent")]
        assert actions == [EnforcementAction.SUSPEND, EnforcementAction.REINSTATE]
        assert service.list_transitions("soc-agent")[0].trigger == CRITICAL_TRIGGER


class TestMonotonicBoundary:
    def test_only_reinstatement_returns_an_agent_to_active(self) -> None:
        service = registered_service()
        service.suspend_agent("soc-agent", reason="critical risk posture")

        # Re-registering is refused, suspension stays suspension, reads change nothing.
        with pytest.raises(AgentAlreadyExistsError):
            service.register_agent(create_agent(status=AgentStatus.ACTIVE))
        service.suspend_agent("soc-agent", reason="again")
        service.get_agent("soc-agent")
        service.list_agents()

        assert service.get_agent("soc-agent").status == AgentStatus.SUSPENDED

        service.reinstate_agent("soc-agent", actor="admin-1", reason="cleared")

        assert service.get_agent("soc-agent").status == AgentStatus.ACTIVE

    def test_runtime_service_cannot_reinstate(self) -> None:
        """The runtime may escalate enforcement; only an operator may relax it."""
        source = inspect.getsource(runtime_service_module)

        assert "reinstate" not in source

    def test_transitions_are_immutable(self) -> None:
        service = registered_service()
        service.suspend_agent("soc-agent", reason="critical risk posture")

        transition = service.list_transitions("soc-agent")[0]

        with pytest.raises(ValidationError):
            transition.actor = "someone-else"


class TestConcurrency:
    def test_concurrent_suspensions_record_one_transition(self) -> None:
        service = registered_service()

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(
                executor.map(
                    lambda _: service.suspend_agent(
                        "soc-agent", reason="critical risk posture"
                    ),
                    range(50),
                )
            )

        assert service.get_agent("soc-agent").status == AgentStatus.SUSPENDED
        assert len(service.list_transitions("soc-agent")) == 1
