"""Tests for AgentService Repository Integration, CAS Epoch Semantics, and Fail-Closed Projection (PR #181).

Verifies the architectural invariants established for Phase 3 Step 2:
1. Authority: AgentRepository and EnforcementStateRepository are the sole authoritative state sources.
2. Canonical Epoch & CAS: Epoch is derived from get_epoch(); CAS conflict raises EnforcementConcurrencyError.
3. Post-CAS Cross-Repository Failure & Fail-Closed Projection: If AgentRepository.save() fails after
   EnforcementStateRepository.record_transition() succeeds, the exception propagates, no 2PC rollback occurs,
   and get_agent() / PolicyEngine project SUSPENDED (fail-closed security).
4. Administrative Lifecycle Priority: DISABLED status remains authoritative over dynamic posture.
   Dynamic suspension on a DISABLED agent produces no EnforcementTransition and creates no dynamic state.
5. Reinstatement Lifecycle: Reinstatement advances recovery epoch; watermark sequences are preserved.
6. Object Isolation: Repositories enforce bidirectional deep defensive copies.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.agent_administrative import Actor
from app.models.agent_enforcement import (
    AgentEnforcementState,
    EnforcementAction,
    EnforcementTransition,
)
from app.models.authorization_result import LifecycleRefusalCode
from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.models.watermark import BaselineWatermark
from app.repositories.in_memory.administrative_state_repository import (
    InMemoryAdministrativeStateRepository,
)
from app.repositories.in_memory.agent_repository import InMemoryAgentRepository
from app.repositories.in_memory.enforcement_state_repository import (
    InMemoryEnforcementStateRepository,
)
from app.repositories.interfaces.enforcement_state_repository import (
    EnforcementStateRepository,
)
from app.services.agent_service import (
    AgentAlreadyExistsError,
    AgentService,
    EnforcementConcurrencyError,
)


def make_test_agent(
    agent_id: str = "agent-repo-test",
    status: AgentStatus = AgentStatus.ACTIVE,
    approved_tools: list[str] | None = None,
) -> Agent:
    return Agent(
        agent_id=agent_id,
        name=f"Agent ({agent_id})",
        owner="security-team",
        risk_tier=RiskTier.HIGH,
        approved_tools=approved_tools or ["file_read"],
        status=status,
    )


def make_test_tool(tool_id: str = "file_read") -> Tool:
    return Tool(
        metadata=ToolMetadata(
            identity=ToolIdentity(tool_id=tool_id, name="Read Tool", description="reads"),
            governance=ToolGovernance(
                risk_level=ToolRiskLevel.LOW,
                required_permissions=["files:read"],
            ),
            capability=ToolCapability(category="filesystem", reads_files=True),
            operational=ToolOperational(),
        )
    )


class RacingEnforcementRepository:
    """Test repository wrapper simulating a concurrent replica committing first via the public protocol."""

    def __init__(self, target: EnforcementStateRepository) -> None:
        self._target = target
        self.simulate_race_on_agent: str | None = None

    def get_state(self, agent_id: str) -> AgentEnforcementState | None:
        return self._target.get_state(agent_id)

    def get_epoch(self, agent_id: str, *, as_of: datetime) -> int:
        return self._target.get_epoch(agent_id, as_of=as_of)

    def list_transitions(
        self,
        agent_id: str | None = None,
    ) -> list[EnforcementTransition]:
        return self._target.list_transitions(agent_id)

    def record_transition(
        self,
        transition: EnforcementTransition,
        new_state: AgentEnforcementState,
        *,
        expected_epoch: int,
    ) -> bool:
        if self.simulate_race_on_agent == transition.agent_id:
            # Simulate a concurrent replica committing at expected_epoch first,
            # using only public protocol methods.
            concurrent_transition = EnforcementTransition(
                transition_id=f"race-competing-{uuid4()}",
                agent_id=transition.agent_id,
                action=EnforcementAction.SUSPEND,
                actor="concurrent-replica",
                reason="concurrent race condition",
                previous_status=AgentStatus.ACTIVE,
                new_status=AgentStatus.SUSPENDED,
                trigger=None,
                occurred_at=datetime.now(timezone.utc),
            )
            concurrent_state = AgentEnforcementState(
                agent_id=transition.agent_id,
                epoch=expected_epoch + 1,
                suspended_at=datetime.now(timezone.utc),
                suspension_reason="concurrent race condition",
            )
            self._target.record_transition(
                transition=concurrent_transition,
                new_state=concurrent_state,
                expected_epoch=expected_epoch,
            )
            self.simulate_race_on_agent = None

        return self._target.record_transition(
            transition=transition,
            new_state=new_state,
            expected_epoch=expected_epoch,
        )


class TestAgentServiceRepositoryAuthority:
    """Verifies that AgentService state lives exclusively in the repositories."""

    def test_registration_and_retrieval_backed_by_agent_repository(self) -> None:
        agent_repo = InMemoryAgentRepository()
        enf_repo = InMemoryEnforcementStateRepository()
        service = AgentService(agent_repo, enf_repo, InMemoryAdministrativeStateRepository())

        agent = make_test_agent("ag-1")
        service.register_and_activate_agent(agent)

        # Repositories are authoritative
        persisted = agent_repo.get("ag-1")
        assert persisted is not None
        assert persisted.agent_id == "ag-1"
        # The raw record carries no lifecycle state (AP.1); the service projects it.
        assert persisted.status == AgentStatus.REGISTERED
        assert service.get_agent("ag-1").status == AgentStatus.ACTIVE

        # Service reads from repository
        retrieved = service.get_agent("ag-1")
        assert retrieved.agent_id == "ag-1"

    def test_duplicate_registration_rejected_against_repository(self) -> None:
        agent_repo = InMemoryAgentRepository()
        enf_repo = InMemoryEnforcementStateRepository()
        service = AgentService(agent_repo, enf_repo, InMemoryAdministrativeStateRepository())

        agent = make_test_agent("ag-dup")
        service.register_and_activate_agent(agent)

        with pytest.raises(AgentAlreadyExistsError):
            service.register_and_activate_agent(agent)

    def test_list_agents_reads_from_agent_repository(self) -> None:
        agent_repo = InMemoryAgentRepository()
        enf_repo = InMemoryEnforcementStateRepository()
        service = AgentService(agent_repo, enf_repo, InMemoryAdministrativeStateRepository())

        service.register_and_activate_agent(make_test_agent("ag-1"))
        service.register_and_activate_agent(make_test_agent("ag-2"))

        listed = service.list_agents()
        assert len(listed) == 2
        assert {a.agent_id for a in listed} == {"ag-1", "ag-2"}


class TestEnforcementCASAndEpochSemantics:
    """Verifies CAS concurrency and canonical epoch derivation."""

    def test_cas_concurrency_conflict_raises_enforcement_concurrency_error(
        self,
    ) -> None:
        agent_repo = InMemoryAgentRepository()
        raw_enf_repo = InMemoryEnforcementStateRepository()
        enf_repo = RacingEnforcementRepository(raw_enf_repo)
        service = AgentService(agent_repo, enf_repo, InMemoryAdministrativeStateRepository())

        service.register_and_activate_agent(make_test_agent("ag-race"))

        # Configure repository wrapper to commit a concurrent transition before service commits,
        # using only the public EnforcementStateRepository protocol (no private _epochs access).
        enf_repo.simulate_race_on_agent = "ag-race"

        with pytest.raises(EnforcementConcurrencyError) as exc_info:
            service.suspend_agent("ag-race", reason="simulated race condition")

        assert "Concurrent modification detected" in str(exc_info.value)
        # Verify AgentRepository was NOT updated by service's failed transition
        persisted_agent = agent_repo.get("ag-race")
        assert persisted_agent is not None
        assert persisted_agent.status == AgentStatus.REGISTERED

    def test_monotonic_epoch_progression_across_suspend_reinstate_cycles(self) -> None:
        agent_repo = InMemoryAgentRepository()
        enf_repo = InMemoryEnforcementStateRepository()
        service = AgentService(agent_repo, enf_repo, InMemoryAdministrativeStateRepository())

        agent_id = "ag-lifecycle"
        service.register_and_activate_agent(make_test_agent(agent_id))

        t0 = datetime.now(timezone.utc)
        assert service.enforcement_epoch(agent_id, as_of=t0) == 0

        # Cycle 1: Suspend -> Reinstate
        service.suspend_agent(agent_id, reason="cycle 1 suspend")
        assert service.get_agent(agent_id).status == AgentStatus.SUSPENDED
        assert (
            service.enforcement_epoch(agent_id, as_of=datetime.now(timezone.utc)) == 0
        )

        service.reinstate_agent(
            agent_id,
            actor="admin-1",
            reason="cycle 1 clearance",
            watermark=BaselineWatermark(agent_id=agent_id, baseline_evidence_sequence=5),
        )
        assert service.get_agent(agent_id).status == AgentStatus.ACTIVE
        t1 = datetime.now(timezone.utc)
        assert service.enforcement_epoch(agent_id, as_of=t1) == 1

        # Cycle 2: Suspend -> Reinstate
        service.suspend_agent(agent_id, reason="cycle 2 suspend")
        assert service.get_agent(agent_id).status == AgentStatus.SUSPENDED
        assert (
            service.enforcement_epoch(agent_id, as_of=datetime.now(timezone.utc)) == 1
        )

        service.reinstate_agent(
            agent_id,
            actor="admin-2",
            reason="cycle 2 clearance",
            watermark=BaselineWatermark(agent_id=agent_id, baseline_evidence_sequence=12),
        )
        assert service.get_agent(agent_id).status == AgentStatus.ACTIVE
        t2 = datetime.now(timezone.utc)
        assert service.enforcement_epoch(agent_id, as_of=t2) == 2

        # Verify historical epoch derivation: as_of t0 sees 0, as_of t1 sees 1, as_of t2 sees 2
        assert service.enforcement_epoch(agent_id, as_of=t0) == 0
        assert service.enforcement_epoch(agent_id, as_of=t1) == 1
        assert service.enforcement_epoch(agent_id, as_of=t2) == 2


class TestEnforcementWritesOnlyItsOwnPlane:
    """What replaced the post-CAS cross-repository failure tests.

    Those tests covered a real hazard: an enforcement transition committed its CAS and
    then wrote ``status`` onto the agent record, so a failure between the two left the two
    stores disagreeing, and the projection had to recover a fail-closed answer from the
    wreckage.

    The flip removes the hazard rather than handling it better. An enforcement transition
    now writes the enforcement plane and nothing else, so there is no second write to fail
    and no window in which the stores can disagree. The tests are replaced rather than
    deleted, because the property worth keeping is the one that makes them unnecessary.
    """

    def test_an_enforcement_transition_does_not_write_the_agent_record(self) -> None:
        agent_repo = InMemoryAgentRepository()
        enf_repo = InMemoryEnforcementStateRepository()
        service = AgentService(
            agent_repo, enf_repo, InMemoryAdministrativeStateRepository()
        )
        agent_id = "ag-no-write"
        service.register_and_activate_agent(make_test_agent(agent_id))

        # Any write to the agent store during a transition is a failure of the invariant,
        # so the store is made to refuse one outright.
        def refuse(agent: Agent) -> None:
            raise AssertionError(
                "an enforcement transition must not write the agent record"
            )

        agent_repo.save = MagicMock(side_effect=refuse)

        service.suspend_agent(agent_id, reason="contained")
        service.reinstate_agent(
            agent_id,
            actor="admin",
            reason="cleared",
            watermark=BaselineWatermark(
                agent_id=agent_id,
                baseline_evidence_sequence=1,
                baseline_agent_sequence=1,
            ),
        )

        agent_repo.save.assert_not_called()

    def test_a_disabled_agent_stays_disabled_through_a_containment_cycle(self) -> None:
        """DISABLED outranks SUSPENDED in the projection, and no enforcement transition
        can make a disabled agent executable (A.5).
        """
        agent_repo = InMemoryAgentRepository()
        enf_repo = InMemoryEnforcementStateRepository()
        service = AgentService(
            agent_repo, enf_repo, InMemoryAdministrativeStateRepository()
        )
        agent_id = "ag-disabled"
        service.register_and_activate_agent(make_test_agent(agent_id))
        service.disable_agent(agent_id, actor=Actor(type="human", id="sec-ops"))

        # Containment is refused for a disabled agent, and the projection still says so.
        service.suspend_agent(agent_id, reason="contained")

        assert service.get_agent(agent_id).status == AgentStatus.DISABLED
        assert (
            service.lifecycle_refusal(agent_id)
            is LifecycleRefusalCode.AGENT_DISABLED
        )

class TestObjectIsolationAndDefensiveCopies:
    """Verifies bidirectional alias isolation between callers and repositories."""

    def test_modifying_retrieved_agent_does_not_mutate_repository(self) -> None:
        agent_repo = InMemoryAgentRepository()
        enf_repo = InMemoryEnforcementStateRepository()
        service = AgentService(agent_repo, enf_repo, InMemoryAdministrativeStateRepository())

        service.register_and_activate_agent(make_test_agent("ag-iso", approved_tools=["file_read"]))

        # Retrieve and mutate caller-owned copy
        caller_copy = service.get_agent("ag-iso")
        caller_copy.approved_tools.append("arbitrary_exec")

        # Repository-owned copy remains pristine
        fresh_read = service.get_agent("ag-iso")
        assert "arbitrary_exec" not in fresh_read.approved_tools
        assert fresh_read.approved_tools == ["file_read"]
