"""Reusable contract tests for EnforcementStateRepository implementations."""

import abc
from datetime import datetime, timezone

import pytest

from app.models.agent import AgentStatus
from app.models.agent_enforcement import (
    AgentEnforcementState,
    EnforcementAction,
    EnforcementTransition,
)
from app.repositories.interfaces.enforcement_state_repository import (
    EnforcementStateRepository,
    EnforcementStateUnavailableError,
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
            agent_id=agent_id, epoch=1, suspended_at=now, suspension_reason="test"
        )

        # Initial epoch is 0
        assert repo.record_transition(t1, s1, expected_epoch=0) is True

        state = repo.get_state(agent_id)
        assert state is not None
        assert state.epoch == 1
        assert state.suspension_reason == "test"
        assert len(repo.list_transitions(agent_id)) == 1

        # Second transition at expected_epoch=1
        t2 = self._sample_transition(
            "t-2",
            agent_id=agent_id,
            action=EnforcementAction.REINSTATE,
            occurred_at=now,
        )
        s2 = AgentEnforcementState(agent_id=agent_id, epoch=2)
        assert repo.record_transition(t2, s2, expected_epoch=1) is True

        assert len(repo.list_transitions(agent_id)) == 2
        assert repo.get_epoch(agent_id, as_of=now) == 1
        state2 = repo.get_state(agent_id)
        assert state2 is not None
        assert state2.epoch == 2

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
            agent_id=agent_id, epoch=1, suspended_at=now, suspension_reason="initial"
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
            agent_id=agent_id, epoch=1, suspension_reason="stale-overwrite"
        )
        assert repo.record_transition(t_stale, s_stale, expected_epoch=0) is False

        # Verify all-or-nothing: state, transitions, and epochs are completely unchanged
        current_state = repo.get_state(agent_id)
        assert current_state is not None
        assert current_state.epoch == 1
        assert current_state.suspension_reason == "initial"
        assert len(repo.list_transitions(agent_id)) == 1

        # Next transition with correct expected_epoch=1 succeeds
        s_next = AgentEnforcementState(
            agent_id=agent_id, epoch=2, suspension_reason="reinstated"
        )
        assert repo.record_transition(t_stale, s_next, expected_epoch=1) is True
        assert len(repo.list_transitions(agent_id)) == 2
        current_state2 = repo.get_state(agent_id)
        assert current_state2 is not None
        assert current_state2.epoch == 2

    def test_deterministic_ordering_with_timestamp_ties(self) -> None:
        """Transitions sharing equal timestamps must deterministically sort by (occurred_at, transition_id)."""
        repo = self.create_repository()
        same_time = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)

        repo.record_transition(
            self._sample_transition(
                "trans-c", agent_id="agent-order", occurred_at=same_time
            ),
            AgentEnforcementState(agent_id="agent-order", epoch=1),
            expected_epoch=0,
        )
        repo.record_transition(
            self._sample_transition(
                "trans-a", agent_id="agent-order", occurred_at=same_time
            ),
            AgentEnforcementState(agent_id="agent-order", epoch=2),
            expected_epoch=1,
        )
        repo.record_transition(
            self._sample_transition(
                "trans-b", agent_id="agent-order", occurred_at=same_time
            ),
            AgentEnforcementState(agent_id="agent-order", epoch=3),
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
            agent_id=agent_id, epoch=1, suspension_reason="orig-reason"
        )
        trans = self._sample_transition("t-1", agent_id=agent_id)

        repo.record_transition(trans, state, expected_epoch=0)

        # Invariant: retrieved state is a distinct instance from original
        retrieved = repo.get_state(agent_id)
        assert retrieved is not None
        assert retrieved is not state

        # Invariant: successive reads produce distinct instances
        retrieved2 = repo.get_state(agent_id)
        assert retrieved2 is not None
        assert retrieved2 is not retrieved

        # Verify list collection and transition object isolation
        t_list = repo.list_transitions(agent_id)
        assert len(t_list) == 1
        assert t_list[0] is not trans
        t_list.clear()
        assert len(repo.list_transitions(agent_id)) == 1

    def test_record_transition_rejects_non_monotonic_epoch_increment(self) -> None:
        """Repository invariant: new_state.epoch must equal expected_epoch + 1 exactly."""
        repo = self.create_repository()
        agent_id = "agent-monotonic-epoch"

        # Attempt 1: epoch did not advance (expected=0, new_state.epoch=0)
        t_same = self._sample_transition("t-same", agent_id=agent_id)
        s_same = AgentEnforcementState(agent_id=agent_id, epoch=0)
        assert repo.record_transition(t_same, s_same, expected_epoch=0) is False
        assert repo.get_state(agent_id) is None
        assert repo.list_transitions(agent_id) == []

        # Attempt 2: epoch skipped ahead (expected=0, new_state.epoch=2)
        t_skip = self._sample_transition("t-skip", agent_id=agent_id)
        s_skip = AgentEnforcementState(agent_id=agent_id, epoch=2)
        assert repo.record_transition(t_skip, s_skip, expected_epoch=0) is False
        assert repo.get_state(agent_id) is None
        assert repo.list_transitions(agent_id) == []

        # Successful transition: expected=0, new_state.epoch=1
        t_valid = self._sample_transition("t-valid", agent_id=agent_id)
        s_valid = AgentEnforcementState(agent_id=agent_id, epoch=1)
        assert repo.record_transition(t_valid, s_valid, expected_epoch=0) is True
        assert repo.get_state(agent_id).epoch == 1

        # Attempt 3 at epoch 1: epoch does not advance (expected=1, new_state.epoch=1)
        t_same2 = self._sample_transition("t-same2", agent_id=agent_id)
        s_same2 = AgentEnforcementState(agent_id=agent_id, epoch=1)
        assert repo.record_transition(t_same2, s_same2, expected_epoch=1) is False
        assert repo.get_state(agent_id).epoch == 1
        assert len(repo.list_transitions(agent_id)) == 1

        # Attempt 4 at epoch 1: epoch skips (expected=1, new_state.epoch=3)
        t_skip2 = self._sample_transition("t-skip2", agent_id=agent_id)
        s_skip2 = AgentEnforcementState(agent_id=agent_id, epoch=3)
        assert repo.record_transition(t_skip2, s_skip2, expected_epoch=1) is False
        assert repo.get_state(agent_id).epoch == 1
        assert len(repo.list_transitions(agent_id)) == 1

    def test_cas_atomicity_guarantee_on_failure(self) -> None:
        """On CAS failure, state, transitions, and epochs are unchanged atomically."""
        repo = self.create_repository()
        agent_id = "agent-cas-atomicity"

        t1 = self._sample_transition("t-1", agent_id=agent_id)
        s1 = AgentEnforcementState(agent_id=agent_id, epoch=1, suspension_reason="orig")
        assert repo.record_transition(t1, s1, expected_epoch=0) is True

        # Failed attempt with bad expected_epoch
        t_fail = self._sample_transition("t-fail", agent_id=agent_id)
        s_fail = AgentEnforcementState(agent_id=agent_id, epoch=3, suspension_reason="corrupt")
        assert repo.record_transition(t_fail, s_fail, expected_epoch=99) is False

        # Verify nothing mutated
        state = repo.get_state(agent_id)
        assert state is not None
        assert state.epoch == 1
        assert state.suspension_reason == "orig"
        assert len(repo.list_transitions(agent_id)) == 1

    # --- Persistence completeness -------------------------------------------------

    def test_the_whole_state_survives_a_round_trip(self) -> None:
        """Every field of AgentEnforcementState survives persistence — not a list of them.

        Asserted as whole-object equality on purpose. The contract is that this repository
        preserves the domain object, so a field added to ``AgentEnforcementState`` later
        fails here in any adapter that forgets to persist it, without anyone remembering
        to extend this test.

        F-01 is what the alternative cost: migration 0002 added ``baseline_agent_sequence``
        and the SQL adapter never read or wrote it, so the value was silently 0 on the
        durable backend while every field-by-field assertion still passed. Do not replace
        this with per-field assertions — that is the omission class it exists to close.

        Every value below is deliberately non-default and distinct: a zero would be
        indistinguishable from a dropped field reconstructing its default, and the two
        baselines differ so that swapping them cannot pass.

        ``recovery_generation`` is 1 rather than an arbitrary distinct value because the
        allocator invariant below bounds it to the stored value or its successor, and from a
        fresh repository that is 0 or 1. It therefore coincides with ``epoch`` here, so this
        test alone cannot catch an adapter that maps one onto the other;
        ``test_the_recovery_generation_is_not_the_epoch_across_a_cycle`` drives them apart
        and is what closes that case.
        """
        repo = self.create_repository()
        agent_id = "agent-roundtrip"

        state = AgentEnforcementState(
            agent_id=agent_id,
            epoch=1,
            suspended_at=datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc),
            suspension_reason="distinct reason text",
            enforcement_baseline_at=datetime(2026, 3, 4, 5, 6, 8, tzinfo=timezone.utc),
            baseline_evidence_sequence=41,
            baseline_agent_sequence=73,
            recovery_generation=1,
            last_transition_at=datetime(2026, 3, 4, 5, 6, 9, tzinfo=timezone.utc),
        )

        assert (
            repo.record_transition(
                self._sample_transition("t-roundtrip", agent_id=agent_id),
                state,
                expected_epoch=0,
            )
            is True
        )

        assert repo.get_state(agent_id) == state

    def test_the_recovery_generation_is_not_the_epoch_across_a_cycle(self) -> None:
        """The two advance at different rates and must be persisted independently.

        ``epoch`` counts every committed transition; ``recovery_generation`` counts only
        committed reinstatements (DR-8(c)). Both are integers, both start at 0, and both are
        called some form of "epoch" in the codebase, so an adapter that maps one column onto
        the other is persistently plausible and invisible to a single-transition test.

        Driven across a full suspend/reinstate cycle, which is the shortest history that
        separates them: epoch reaches 2 while the generation reaches 1.
        """
        repo = self.create_repository()
        agent_id = "agent-generation-vs-epoch"

        # Containment: a transition, but not a recovery.
        assert (
            repo.record_transition(
                self._sample_transition(
                    "t-suspend", agent_id=agent_id, action=EnforcementAction.SUSPEND
                ),
                AgentEnforcementState(agent_id=agent_id, epoch=1, recovery_generation=0),
                expected_epoch=0,
            )
            is True
        )
        contained = repo.get_state(agent_id)
        assert contained is not None
        assert contained.epoch == 1
        assert contained.recovery_generation == 0

        # Recovery: both advance, by different amounts, to different values.
        assert (
            repo.record_transition(
                self._sample_transition(
                    "t-reinstate", agent_id=agent_id, action=EnforcementAction.REINSTATE
                ),
                AgentEnforcementState(agent_id=agent_id, epoch=2, recovery_generation=1),
                expected_epoch=1,
            )
            is True
        )
        recovered = repo.get_state(agent_id)
        assert recovered is not None
        assert recovered.epoch == 2
        assert recovered.recovery_generation == 1
        assert recovered.recovery_generation != recovered.epoch

    def test_record_transition_refuses_a_non_monotonic_recovery_generation(self) -> None:
        """Repository invariant: the generation may only hold or advance by exactly one.

        Raised rather than reported as a CAS miss, and the distinction is the point. A CAS
        miss means "another transition won the race, re-read and retry"; a generation that
        moved backwards or skipped is a programming error that no retry repairs, so a caller
        looping on ``False`` would spin forever against a defect. The repository is the
        boundary that commits, so it is the boundary that must refuse.

        A backwards generation is the one L.6 cares about directly: a durable namespace must
        not be restored below a durable record that already references it, and a Finding
        stamped with generation 2 outlives a state rolled back to 1.
        """
        repo = self.create_repository()
        agent_id = "agent-generation-monotonic"

        # Establish generation 1 at epoch 1.
        assert (
            repo.record_transition(
                self._sample_transition("t-base", agent_id=agent_id),
                AgentEnforcementState(agent_id=agent_id, epoch=1, recovery_generation=1),
                expected_epoch=0,
            )
            is True
        )

        # Backwards.
        with pytest.raises(EnforcementStateUnavailableError):
            repo.record_transition(
                self._sample_transition("t-back", agent_id=agent_id),
                AgentEnforcementState(agent_id=agent_id, epoch=2, recovery_generation=0),
                expected_epoch=1,
            )

        # Skipped ahead.
        with pytest.raises(EnforcementStateUnavailableError):
            repo.record_transition(
                self._sample_transition("t-skip", agent_id=agent_id),
                AgentEnforcementState(agent_id=agent_id, epoch=2, recovery_generation=3),
                expected_epoch=1,
            )

        # Neither refusal committed anything.
        state = repo.get_state(agent_id)
        assert state is not None
        assert state.epoch == 1
        assert state.recovery_generation == 1
        assert len(repo.list_transitions(agent_id)) == 1

        # Holding is permitted (a suspension), and so is advancing by exactly one.
        assert (
            repo.record_transition(
                self._sample_transition("t-hold", agent_id=agent_id),
                AgentEnforcementState(agent_id=agent_id, epoch=2, recovery_generation=1),
                expected_epoch=1,
            )
            is True
        )
        assert repo.get_state(agent_id).recovery_generation == 1
        assert (
            repo.record_transition(
                self._sample_transition("t-advance", agent_id=agent_id),
                AgentEnforcementState(agent_id=agent_id, epoch=3, recovery_generation=2),
                expected_epoch=2,
            )
            is True
        )
        assert repo.get_state(agent_id).recovery_generation == 2

    def test_advancing_one_baseline_leaves_the_other_namespace_alone(self) -> None:
        """The two baselines are positions in different monotonic namespaces.

        ``baseline_evidence_sequence`` counts findings and ``baseline_agent_sequence``
        counts session events, allocated by different authorities at different rates. A
        transition advancing one must not move or reset the other — that asymmetry is the
        shape the original defect took.
        """
        repo = self.create_repository()
        agent_id = "agent-namespaces"

        initial = AgentEnforcementState(
            agent_id=agent_id,
            epoch=1,
            baseline_evidence_sequence=41,
            baseline_agent_sequence=73,
        )
        assert (
            repo.record_transition(
                self._sample_transition("t-ns-1", agent_id=agent_id),
                initial,
                expected_epoch=0,
            )
            is True
        )

        assert (
            repo.record_transition(
                self._sample_transition(
                    "t-ns-2", agent_id=agent_id, action=EnforcementAction.REINSTATE
                ),
                initial.model_copy(
                    update={"epoch": 2, "baseline_evidence_sequence": 58}
                ),
                expected_epoch=1,
            )
            is True
        )

        loaded = repo.get_state(agent_id)
        assert loaded is not None
        assert loaded.baseline_evidence_sequence == 58, "the evidence baseline advanced"
        assert loaded.baseline_agent_sequence == 73, "the agent baseline is untouched"

    def test_an_advancing_agent_baseline_persists_through_an_update(self) -> None:
        """A reinstatement moves the agent watermark, and the new value must be stored.

        Separate from the test above because that one holds this value constant, which
        cannot tell "the update wrote the same value" from "the update never wrote it" —
        a state created once and never updated keeps its inserted value either way. Only
        a transition that *changes* it distinguishes the two.
        """
        repo = self.create_repository()
        agent_id = "agent-advancing-baseline"

        initial = AgentEnforcementState(
            agent_id=agent_id,
            epoch=1,
            baseline_evidence_sequence=41,
            baseline_agent_sequence=73,
        )
        assert (
            repo.record_transition(
                self._sample_transition("t-adv-1", agent_id=agent_id),
                initial,
                expected_epoch=0,
            )
            is True
        )

        assert (
            repo.record_transition(
                self._sample_transition(
                    "t-adv-2", agent_id=agent_id, action=EnforcementAction.REINSTATE
                ),
                initial.model_copy(update={"epoch": 2, "baseline_agent_sequence": 150}),
                expected_epoch=1,
            )
            is True
        )

        loaded = repo.get_state(agent_id)
        assert loaded is not None
        assert loaded.baseline_agent_sequence == 150, "the agent baseline advanced"
        assert loaded.baseline_evidence_sequence == 41, "the evidence baseline is untouched"
