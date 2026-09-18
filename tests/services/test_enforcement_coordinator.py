"""Administrative recovery from containment (M2b Step 5).

Reinstatement spans two independent stores, so the contract is convergence rather than
atomicity:

    success      → ACTIVE + issuance open
    partial      → ACTIVE + issuance closed   (fail-closed, surfaced, repairable)
    retry        → ACTIVE + issuance open

and, throughout, no runtime path may recover a contained agent.
"""

import inspect

import pytest

import app.services.runtime_service as runtime_service_module
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import Decision
from app.models.execution_binding import ExecutionBinding
from app.runtime.execution_authority import ExecutionAuthority
from app.services.agent_service import (
    AgentNotFoundError,
    AgentNotSuspendedError,
    AgentService,
)
from app.services.enforcement_coordinator import (
    EnforcementCoordinator,
    ReinstatementIncompleteError,
)

AGENT_ID = "contained-agent"
BINDING = ExecutionBinding.from_operation("file_read", {"path": "notes.txt"})


class RefusingAuthority(ExecutionAuthority):
    """An authority whose gate cannot be reopened, to exercise partial failure."""

    def __init__(self) -> None:
        super().__init__()
        self.repair_allowed = False

    def resume_issuance(self, agent_id: str) -> None:
        if not self.repair_allowed:
            return  # silently fails to reopen
        super().resume_issuance(agent_id)


def build(authority: ExecutionAuthority | None = None):
    agents = AgentService()
    agents.register_agent(
        Agent(
            agent_id=AGENT_ID,
            name="Contained",
            owner="security-team",
            risk_tier=RiskTier.HIGH,
            approved_tools=["file_read"],
            status=AgentStatus.ACTIVE,
        )
    )
    authority = authority or ExecutionAuthority()
    return agents, authority, EnforcementCoordinator(agents, authority)


def contain(agents: AgentService, authority: ExecutionAuthority) -> None:
    """Reproduce what the runtime does when it contains an agent."""
    authority.suspend_issuance(AGENT_ID)
    agents.suspend_agent(AGENT_ID, reason="critical risk posture")


class TestSuccessfulReinstatement:
    def test_agent_returns_to_service_with_issuance_open(self) -> None:
        agents, authority, coordinator = build()
        contain(agents, authority)

        agent = coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        assert agent.status == AgentStatus.ACTIVE
        assert authority.issuance_suspended(AGENT_ID) is False
        assert authority.issue(BINDING, Decision.ALLOW, agent_id=AGENT_ID) is not None

    def test_reinstatement_is_attributed(self) -> None:
        agents, authority, coordinator = build()
        contain(agents, authority)

        coordinator.reinstate(AGENT_ID, actor="admin-1", reason="false positive")

        transition = agents.list_transitions(AGENT_ID)[-1]
        assert transition.actor == "admin-1"
        assert transition.reason == "false positive"

    def test_grants_revoked_during_containment_stay_revoked(self) -> None:
        agents, authority, coordinator = build()
        revoked = authority.issue(BINDING, Decision.ALLOW, agent_id=AGENT_ID)
        contain(agents, authority)

        coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        from app.runtime.execution_authority import (
            ExecutionBindingError,
            ExecutionRefusalReason,
        )

        with pytest.raises(ExecutionBindingError) as refusal:
            authority.verify_and_consume(revoked, BINDING)
        assert refusal.value.reason == ExecutionRefusalReason.REVOKED


class TestRefusedReinstatement:
    def test_an_unknown_agent_is_refused(self) -> None:
        _, _, coordinator = build()

        with pytest.raises(AgentNotFoundError):
            coordinator.reinstate("absent", actor="admin-1", reason="investigated")

    def test_an_active_agent_is_refused(self) -> None:
        _, authority, coordinator = build()

        with pytest.raises(AgentNotSuspendedError):
            coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        assert authority.issuance_suspended(AGENT_ID) is False

    @pytest.mark.parametrize(("actor", "reason"), [("", "why"), ("admin-1", "  ")])
    def test_reinstatement_must_be_attributed(self, actor: str, reason: str) -> None:
        agents, authority, coordinator = build()
        contain(agents, authority)

        with pytest.raises(ValueError):
            coordinator.reinstate(AGENT_ID, actor=actor, reason=reason)

        # The refusal changed nothing: containment still holds.
        assert agents.get_agent(AGENT_ID).status == AgentStatus.SUSPENDED
        assert authority.issuance_suspended(AGENT_ID) is True


class TestPartialFailureConverges:
    def test_a_failed_gate_reopen_is_surfaced_not_reported_as_success(self) -> None:
        authority = RefusingAuthority()
        agents, authority, coordinator = build(authority)
        contain(agents, authority)

        with pytest.raises(ReinstatementIncompleteError):
            coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

    def test_the_partial_state_is_fail_closed(self) -> None:
        authority = RefusingAuthority()
        agents, authority, coordinator = build(authority)
        contain(agents, authority)

        with pytest.raises(ReinstatementIncompleteError):
            coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        # Active to policy, but no execution authority can be obtained.
        assert agents.get_agent(AGENT_ID).status == AgentStatus.ACTIVE
        assert authority.issuance_suspended(AGENT_ID) is True
        assert authority.issue(BINDING, Decision.ALLOW, agent_id=AGENT_ID) is None

    def test_retry_repairs_the_asymmetry(self) -> None:
        authority = RefusingAuthority()
        agents, authority, coordinator = build(authority)
        contain(agents, authority)
        with pytest.raises(ReinstatementIncompleteError):
            coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        authority.repair_allowed = True
        repaired = coordinator.repair(AGENT_ID)

        assert repaired.status == AgentStatus.ACTIVE
        assert authority.issuance_suspended(AGENT_ID) is False
        assert authority.issue(BINDING, Decision.ALLOW, agent_id=AGENT_ID) is not None

    def test_repair_cannot_recover_a_suspended_agent(self) -> None:
        """Repair reopens a gate; it is not a second route out of containment."""
        agents, authority, coordinator = build()
        contain(agents, authority)

        with pytest.raises(ReinstatementIncompleteError):
            coordinator.repair(AGENT_ID)

        assert agents.get_agent(AGENT_ID).status == AgentStatus.SUSPENDED
        assert authority.issuance_suspended(AGENT_ID) is True


class TestRuntimeCannotRecover:
    def test_no_runtime_path_reinstates_or_reopens_issuance(self) -> None:
        """Runtime enforcement is one-way: containment yes, recovery no."""
        source = inspect.getsource(runtime_service_module)

        assert "reinstate" not in source
        assert "resume_issuance" not in source

    def test_the_coordinator_never_contains(self) -> None:
        import app.services.enforcement_coordinator as coordinator_module

        source = inspect.getsource(coordinator_module)

        assert "suspend_agent" not in source
        assert "suspend_issuance" not in source
