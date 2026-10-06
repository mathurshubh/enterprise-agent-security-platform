"""Reusable contract tests for AdministrativeStateRepository implementations (ADR-030 AP.11).

One suite, every adapter. The SQL adapter does not yet exist; when it does it binds here
rather than growing its own tests, so the two cannot drift into different semantics.
"""

import abc
from datetime import datetime, timezone

import pytest

from app.models.agent_administrative import (
    Actor,
    AdministrativeAction,
    AdministrativeLifecycleState,
    AdministrativeTransition,
    AgentAdministrativeState,
)
from app.repositories.interfaces.administrative_state_repository import (
    AdministrativeStateRepository,
    AdministrativeTransitionInvariantError,
)

ADMIN = Actor(type="human", id="sec-ops-1")


class BaseAdministrativeStateRepositoryContractTests(abc.ABC):
    """Abstract contract suite for any AdministrativeStateRepository adapter."""

    @abc.abstractmethod
    def create_repository(self) -> AdministrativeStateRepository:
        """Factory for a fresh, empty repository under test."""
        raise NotImplementedError

    # --- helpers ----------------------------------------------------------------

    def _transition(
        self,
        agent_id: str,
        *,
        transition_id: str,
        action: AdministrativeAction,
        previous_state: AdministrativeLifecycleState | None,
        new_state: AdministrativeLifecycleState,
        version_before: int,
        occurred_at: datetime | None = None,
    ) -> AdministrativeTransition:
        return AdministrativeTransition(
            transition_id=transition_id,
            agent_id=agent_id,
            action=action,
            actor=ADMIN,
            reason="contract test",
            previous_state=previous_state,
            new_state=new_state,
            administrative_version_before=version_before,
            administrative_version_after=version_before + 1,
            correlation_id=f"corr-{transition_id}",
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )

    def _register(self, repo: AdministrativeStateRepository, agent_id: str) -> None:
        """Commit the registration transition, the only legal first step."""
        assert (
            repo.record_transition(
                self._transition(
                    agent_id,
                    transition_id=f"t-reg-{agent_id}",
                    action=AdministrativeAction.REGISTER,
                    previous_state=None,
                    new_state=AdministrativeLifecycleState.REGISTERED,
                    version_before=0,
                ),
                AgentAdministrativeState(
                    agent_id=agent_id,
                    state=AdministrativeLifecycleState.REGISTERED,
                    administrative_version=1,
                ),
                expected_version=0,
            )
            is True
        )

    # --- absence ----------------------------------------------------------------

    def test_absence_is_reported_as_none_not_as_registered(self) -> None:
        """No record means the state is not establishable (L.3).

        Asserted explicitly because the superseded model made these indistinguishable:
        ``REGISTERED`` was the Agent default, so an unregistered agent and a registered
        one presented the same value. L.10 turns None into
        ADMINISTRATIVE_STATE_UNAVAILABLE, which is not a lifecycle state.
        """
        repo = self.create_repository()
        assert repo.get_state("agent-absent") is None
        assert repo.list_transitions("agent-absent") == []

    # --- round-trip -------------------------------------------------------------

    def test_the_whole_state_survives_a_round_trip(self) -> None:
        """Whole-object equality, with every value non-default and pairwise distinct.

        Asserted as whole-object equality on purpose, so a field added to
        ``AgentAdministrativeState`` later fails here in any adapter that forgets to
        persist it, without anyone remembering to extend this test.

        The values are chosen, not incidental. This repository has twice shipped a
        dropped column that a round-trip test did not catch -- F-01's
        ``baseline_agent_sequence`` and DR-8(c)'s ``recovery_generation`` -- both times
        because the test value equalled the field's default and a dropped field
        reconstructs its default. ``administrative_version`` is 2 rather than 1 so it
        cannot be confused with a freshly registered record, and ``last_transition_at``
        is set so a dropped timestamp cannot pass as None.
        """
        repo = self.create_repository()
        agent_id = "agent-roundtrip"
        self._register(repo, agent_id)

        state = AgentAdministrativeState(
            agent_id=agent_id,
            state=AdministrativeLifecycleState.ACTIVE,
            administrative_version=2,
            last_transition_at=datetime(2026, 4, 5, 6, 7, 8, tzinfo=timezone.utc),
        )
        assert (
            repo.record_transition(
                self._transition(
                    agent_id,
                    transition_id="t-activate",
                    action=AdministrativeAction.ACTIVATE,
                    previous_state=AdministrativeLifecycleState.REGISTERED,
                    new_state=AdministrativeLifecycleState.ACTIVE,
                    version_before=1,
                ),
                state,
                expected_version=1,
            )
            is True
        )

        assert repo.get_state(agent_id) == state

    # --- compare-and-set --------------------------------------------------------

    def test_registration_is_the_only_legal_first_transition(self) -> None:
        """An agent cannot be activated into existence (AP.5)."""
        repo = self.create_repository()

        with pytest.raises(AdministrativeTransitionInvariantError):
            repo.record_transition(
                self._transition(
                    "agent-skip",
                    transition_id="t-skip",
                    action=AdministrativeAction.ACTIVATE,
                    previous_state=None,
                    new_state=AdministrativeLifecycleState.ACTIVE,
                    version_before=0,
                ),
                AgentAdministrativeState(
                    agent_id="agent-skip",
                    state=AdministrativeLifecycleState.ACTIVE,
                    administrative_version=1,
                ),
                expected_version=0,
            )

        assert repo.get_state("agent-skip") is None
        assert repo.list_transitions("agent-skip") == []

    def test_a_stale_expected_version_loses_the_race_and_returns_false(self) -> None:
        """A lost update returns False -- it is retryable, and retrying repairs it."""
        repo = self.create_repository()
        agent_id = "agent-cas"
        self._register(repo, agent_id)

        # The caller believes no record exists; one does, at version 1.
        assert (
            repo.record_transition(
                self._transition(
                    agent_id,
                    transition_id="t-stale",
                    action=AdministrativeAction.REGISTER,
                    previous_state=None,
                    new_state=AdministrativeLifecycleState.REGISTERED,
                    version_before=0,
                ),
                AgentAdministrativeState(
                    agent_id=agent_id,
                    state=AdministrativeLifecycleState.REGISTERED,
                    administrative_version=1,
                ),
                expected_version=0,
            )
            is False
        )

    def test_a_failed_cas_mutates_neither_state_nor_history(self) -> None:
        """The load-bearing property, which the returned boolean does not carry.

        A failed transition that advanced the ledger, or left the state half-replaced,
        would still satisfy an assertion on the return value alone. Atomicity is what
        makes a refusal safe to retry; without it a retry compounds the damage.
        """
        repo = self.create_repository()
        agent_id = "agent-atomic"
        self._register(repo, agent_id)
        before_state = repo.get_state(agent_id)
        before_history = repo.list_transitions(agent_id)

        assert (
            repo.record_transition(
                self._transition(
                    agent_id,
                    transition_id="t-lost",
                    action=AdministrativeAction.ACTIVATE,
                    previous_state=AdministrativeLifecycleState.REGISTERED,
                    new_state=AdministrativeLifecycleState.ACTIVE,
                    version_before=7,
                ),
                AgentAdministrativeState(
                    agent_id=agent_id,
                    state=AdministrativeLifecycleState.ACTIVE,
                    administrative_version=8,
                ),
                expected_version=7,
            )
            is False
        )

        assert repo.get_state(agent_id) == before_state
        assert repo.list_transitions(agent_id) == before_history

    def test_an_invariant_violation_raises_rather_than_returning_false(self) -> None:
        """AP.4: the two outcomes must not be conflated.

        ``False`` tells a caller to re-read and retry. A version that does not advance by
        exactly one will not improve on retry, so reporting it as a lost update invites a
        caller to loop against a programming error. The distinction is the contract, not
        an implementation detail.
        """
        repo = self.create_repository()
        agent_id = "agent-invariant"
        self._register(repo, agent_id)

        with pytest.raises(AdministrativeTransitionInvariantError):
            repo.record_transition(
                self._transition(
                    agent_id,
                    transition_id="t-skip-version",
                    action=AdministrativeAction.ACTIVATE,
                    previous_state=AdministrativeLifecycleState.REGISTERED,
                    new_state=AdministrativeLifecycleState.ACTIVE,
                    version_before=1,
                ),
                AgentAdministrativeState(
                    agent_id=agent_id,
                    state=AdministrativeLifecycleState.ACTIVE,
                    administrative_version=3,  # skips 2
                ),
                expected_version=1,
            )

        assert repo.get_state(agent_id).administrative_version == 1
        assert len(repo.list_transitions(agent_id)) == 1

    def test_a_version_skip_is_refused_even_when_the_ledger_agrees_with_it(self) -> None:
        """Isolates the version-advance check from the ledger-consistency check.

        Found by mutation: removing the version-advance check left every other test
        green, because a skipping ``new_state`` normally disagrees with the ledger entry
        too, so the ledger check fired first and masked it. A caller that builds a
        *coherent* ledger entry for the skip -- before 1, after 3, state 3 -- satisfies
        the ledger check entirely, and only the version-advance check stands between that
        and a committed gap in the version chain.

        A gap matters because the chain is what makes the ledger self-checking: with one
        missing, a reader cannot distinguish an unrecorded transition from a renumbered
        one.
        """
        repo = self.create_repository()
        agent_id = "agent-version-skip"
        self._register(repo, agent_id)

        skipping = AdministrativeTransition(
            transition_id="t-coherent-skip",
            agent_id=agent_id,
            action=AdministrativeAction.ACTIVATE,
            actor=ADMIN,
            reason="contract test",
            previous_state=AdministrativeLifecycleState.REGISTERED,
            new_state=AdministrativeLifecycleState.ACTIVE,
            administrative_version_before=1,
            administrative_version_after=3,
            correlation_id="corr-coherent-skip",
        )

        with pytest.raises(AdministrativeTransitionInvariantError):
            repo.record_transition(
                skipping,
                AgentAdministrativeState(
                    agent_id=agent_id,
                    state=AdministrativeLifecycleState.ACTIVE,
                    administrative_version=3,
                ),
                expected_version=1,
            )

        assert repo.get_state(agent_id).administrative_version == 1
        assert len(repo.list_transitions(agent_id)) == 1

    def test_a_refused_invariant_leaves_the_ledger_untouched(self) -> None:
        """Atomicity on the raising path, not only on the CAS-miss path.

        ``test_a_failed_cas_mutates_neither_state_nor_history`` covers the lost update.
        This covers the other refusal: an invariant violation must also leave no trace,
        or a rejected transition would still appear in the authoritative evidence.
        """
        repo = self.create_repository()
        agent_id = "agent-refusal-atomic"
        self._register(repo, agent_id)
        before_history = repo.list_transitions(agent_id)

        with pytest.raises(AdministrativeTransitionInvariantError):
            repo.record_transition(
                self._transition(
                    agent_id,
                    transition_id="t-illegal",
                    action=AdministrativeAction.ACTIVATE,
                    previous_state=None,
                    new_state=AdministrativeLifecycleState.REGISTERED,
                    version_before=1,
                ),
                AgentAdministrativeState(
                    agent_id=agent_id,
                    state=AdministrativeLifecycleState.REGISTERED,
                    administrative_version=2,
                ),
                expected_version=1,
            )

        assert repo.list_transitions(agent_id) == before_history

    # --- transition graph -------------------------------------------------------

    def test_disabled_is_terminal(self) -> None:
        """No transition leaves DISABLED (AP.5).

        Including back to REGISTERED, which is the shape a 'reset the agent' feature
        would take. Re-enablement would be a separately defined, separately authorized
        transition; it is not this one, and it is not reinstatement.
        """
        repo = self.create_repository()
        agent_id = "agent-terminal"
        self._register(repo, agent_id)
        assert (
            repo.record_transition(
                self._transition(
                    agent_id,
                    transition_id="t-disable",
                    action=AdministrativeAction.DISABLE,
                    previous_state=AdministrativeLifecycleState.REGISTERED,
                    new_state=AdministrativeLifecycleState.DISABLED,
                    version_before=1,
                ),
                AgentAdministrativeState(
                    agent_id=agent_id,
                    state=AdministrativeLifecycleState.DISABLED,
                    administrative_version=2,
                ),
                expected_version=1,
            )
            is True
        )

        for target in (
            AdministrativeLifecycleState.ACTIVE,
            AdministrativeLifecycleState.REGISTERED,
        ):
            with pytest.raises(AdministrativeTransitionInvariantError):
                repo.record_transition(
                    self._transition(
                        agent_id,
                        transition_id=f"t-escape-{target.value}",
                        action=AdministrativeAction.ACTIVATE,
                        previous_state=AdministrativeLifecycleState.DISABLED,
                        new_state=target,
                        version_before=2,
                    ),
                    AgentAdministrativeState(
                        agent_id=agent_id,
                        state=target,
                        administrative_version=3,
                    ),
                    expected_version=2,
                )

        assert repo.get_state(agent_id).state == AdministrativeLifecycleState.DISABLED
        assert len(repo.list_transitions(agent_id)) == 2

    def test_a_ledger_entry_must_describe_the_transition_it_records(self) -> None:
        """Evidence that disagrees with the state it records is not evidence of it.

        The ledger is authoritative lifecycle evidence (AP.6), not a caller-supplied
        annotation, so its endpoints and versions are validated against what is being
        committed rather than trusted.
        """
        repo = self.create_repository()
        agent_id = "agent-ledger"
        self._register(repo, agent_id)

        with pytest.raises(AdministrativeTransitionInvariantError):
            repo.record_transition(
                # Claims it came from ACTIVE; the record says REGISTERED.
                self._transition(
                    agent_id,
                    transition_id="t-mismatch",
                    action=AdministrativeAction.DISABLE,
                    previous_state=AdministrativeLifecycleState.ACTIVE,
                    new_state=AdministrativeLifecycleState.DISABLED,
                    version_before=1,
                ),
                AgentAdministrativeState(
                    agent_id=agent_id,
                    state=AdministrativeLifecycleState.DISABLED,
                    administrative_version=2,
                ),
                expected_version=1,
            )

        assert len(repo.list_transitions(agent_id)) == 1

    # --- history ----------------------------------------------------------------

    def test_history_is_append_only_and_deterministically_ordered(self) -> None:
        repo = self.create_repository()
        agent_id = "agent-history"
        self._register(repo, agent_id)
        assert (
            repo.record_transition(
                self._transition(
                    agent_id,
                    transition_id="t-act",
                    action=AdministrativeAction.ACTIVATE,
                    previous_state=AdministrativeLifecycleState.REGISTERED,
                    new_state=AdministrativeLifecycleState.ACTIVE,
                    version_before=1,
                ),
                AgentAdministrativeState(
                    agent_id=agent_id,
                    state=AdministrativeLifecycleState.ACTIVE,
                    administrative_version=2,
                ),
                expected_version=1,
            )
            is True
        )

        history = repo.list_transitions(agent_id)
        assert [t.action for t in history] == [
            AdministrativeAction.REGISTER,
            AdministrativeAction.ACTIVATE,
        ]
        # Versions chain without gaps, which is what makes the ledger self-checking.
        assert [
            (t.administrative_version_before, t.administrative_version_after)
            for t in history
        ] == [(0, 1), (1, 2)]

    def test_history_is_isolated_between_agents(self) -> None:
        repo = self.create_repository()
        self._register(repo, "agent-a")
        self._register(repo, "agent-b")

        assert len(repo.list_transitions("agent-a")) == 1
        assert len(repo.list_transitions("agent-b")) == 1
        assert len(repo.list_transitions()) == 2
