"""Reusable contract tests for EnforcementStateRepository implementations."""

import abc
from datetime import datetime, timezone

from app.models.agent import AgentStatus
from app.models.agent_enforcement import (
    AgentEnforcementState,
    EnforcementAction,
    EnforcementTransition,
)
from app.repositories.interfaces.enforcement_state_repository import (
    EnforcementStateRepository,
)


class BaseEnforcementStateRepositoryContractTests(abc.ABC):
    """Abstract contract test suite for any EnforcementStateRepository adapter."""

    @abc.abstractmethod
    def create_repository(self) -> EnforcementStateRepository:
        """Factory method to construct a fresh, empty repository under test."""
        raise NotImplementedError

    def _sample_transition(
        self,
        transition_id: str = "t-1",
        agent_id: str = "agent-1",
        action: EnforcementAction = EnforcementAction.SUSPEND,
        occurred_at: datetime | None = None,
    ) -> EnforcementTransition:
        return EnforcementTransition(
            transition_id=transition_id,
            agent_id=agent_id,
            action=action,
            actor="runtime" if action == EnforcementAction.SUSPEND else "sec-ops",
            reason="Violation observed"
            if action == EnforcementAction.SUSPEND
            else "Remediated",
            previous_status=AgentStatus.ACTIVE
            if action == EnforcementAction.SUSPEND
            else AgentStatus.SUSPENDED,
            new_status=AgentStatus.SUSPENDED
            if action == EnforcementAction.SUSPEND
            else AgentStatus.ACTIVE,
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )

    def test_get_uninitialized_state_returns_none(self) -> None:
        repo = self.create_repository()
        assert repo.get_state("non-existent-agent") is None
        assert repo.list_transitions("non-existent-agent") == []
        assert (
            repo.get_epoch("non-existent-agent", as_of=datetime.now(timezone.utc)) == 0
        )

    def test_record_transition_cas_success_advances_epoch(self) -> None:
        repo = self.create_repository()
        agent_id = "agent-cas-1"
        now = datetime.now(timezone.utc)

        t1 = self._sample_transition(
            "t-1", agent_id=agent_id, action=EnforcementAction.SUSPEND, occurred_at=now
        )
        s1 = AgentEnforcementState(
            agent_id=agent_id, suspended_at=now, suspension_reason="test"
        )

        # Initial epoch is 0
        assert repo.record_transition(t1, s1, expected_epoch=0) is True

        state = repo.get_state(agent_id)
        assert state is not None
        assert state.suspension_reason == "test"
        assert len(repo.list_transitions(agent_id)) == 1

        # Second transition at expected_epoch=1
        t2 = self._sample_transition(
            "t-2",
            agent_id=agent_id,
            action=EnforcementAction.REINSTATE,
            occurred_at=now,
        )
        s2 = AgentEnforcementState(agent_id=agent_id)
        assert repo.record_transition(t2, s2, expected_epoch=1) is True

        assert len(repo.list_transitions(agent_id)) == 2
        assert repo.get_epoch(agent_id, as_of=now) == 1

    def test_record_transition_cas_mismatch_fails_closed_and_leaves_state_unchanged(
        self,
    ) -> None:
        repo = self.create_repository()
        agent_id = "agent-cas-2"
        now = datetime.now(timezone.utc)

        t1 = self._sample_transition(
            "t-1", agent_id=agent_id, action=EnforcementAction.SUSPEND, occurred_at=now
        )
        s1 = AgentEnforcementState(
            agent_id=agent_id, suspended_at=now, suspension_reason="initial"
        )
        assert repo.record_transition(t1, s1, expected_epoch=0) is True

        # Stale attempt: expected_epoch=0 when persisted epoch is 1
        t_stale = self._sample_transition(
            "t-stale",
            agent_id=agent_id,
            action=EnforcementAction.REINSTATE,
            occurred_at=now,
        )
        s_stale = AgentEnforcementState(
            agent_id=agent_id, suspension_reason="stale-overwrite"
        )
        assert repo.record_transition(t_stale, s_stale, expected_epoch=0) is False

        # Verify all-or-nothing: state, transitions, and epochs are completely unchanged
        current_state = repo.get_state(agent_id)
        assert current_state is not None
        assert current_state.suspension_reason == "initial"
        assert len(repo.list_transitions(agent_id)) == 1

        # Next transition with correct expected_epoch=1 succeeds
        assert repo.record_transition(t_stale, s_stale, expected_epoch=1) is True
        assert len(repo.list_transitions(agent_id)) == 2

    def test_deterministic_ordering_with_timestamp_ties(self) -> None:
        """Transitions sharing equal timestamps must deterministically sort by (occurred_at, transition_id)."""
        repo = self.create_repository()
        same_time = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
        state = AgentEnforcementState(agent_id="agent-order")

        repo.record_transition(
            self._sample_transition(
                "trans-c", agent_id="agent-order", occurred_at=same_time
            ),
            state,
            expected_epoch=0,
        )
        repo.record_transition(
            self._sample_transition(
                "trans-a", agent_id="agent-order", occurred_at=same_time
            ),
            state,
            expected_epoch=1,
        )
        repo.record_transition(
            self._sample_transition(
                "trans-b", agent_id="agent-order", occurred_at=same_time
            ),
            state,
            expected_epoch=2,
        )

        transitions = repo.list_transitions("agent-order")
        assert [t.transition_id for t in transitions] == [
            "trans-a",
            "trans-b",
            "trans-c",
        ]

    def test_defensive_copy_isolation(self) -> None:
        repo = self.create_repository()
        agent_id = "agent-iso-enf"
        state = AgentEnforcementState(
            agent_id=agent_id, suspension_reason="orig-reason"
        )
        trans = self._sample_transition("t-1", agent_id=agent_id)

        repo.record_transition(trans, state, expected_epoch=0)

        # Mutate retrieved state
        retrieved = repo.get_state(agent_id)
        assert retrieved is not None

        # Verify list collection isolation
        t_list = repo.list_transitions(agent_id)
        t_list.clear()
        assert len(repo.list_transitions(agent_id)) == 1
