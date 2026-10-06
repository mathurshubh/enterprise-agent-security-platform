"""Administrative lifecycle model invariants (ADR-024 F-09, ADR-030 AP.2/AP.5)."""

import pytest
from pydantic import ValidationError

from app.models.agent_administrative import (
    ADMINISTRATIVE_TRANSITION_ACTIONS,
    LEGAL_ADMINISTRATIVE_TRANSITIONS,
    Actor,
    AdministrativeAction,
    AdministrativeLifecycleState,
    AgentAdministrativeState,
    is_legal_administrative_transition,
)


@pytest.mark.security_invariant
def test_every_administrative_state_is_classified_in_the_transition_graph() -> None:
    """No lifecycle state may be left unconsidered by the graph.

    Guards the omission rather than any one transition. A state added to the enum without
    a decision here would otherwise inherit whichever default the lookup happens to have,
    which is the shape of the defect F-09.A removed from the execution gate: REGISTERED
    was executable because nobody had classified it, not because anyone decided it should
    be.
    """
    classified = set(LEGAL_ADMINISTRATIVE_TRANSITIONS) - {None}
    assert classified == set(AdministrativeLifecycleState)


@pytest.mark.security_invariant
def test_the_legal_transition_graph_is_exactly_the_specified_one() -> None:
    """ADR-024 A.3 / AP.5, asserted as the whole graph rather than sampled edges.

    Written as an equality so an edge *added* fails too. Sampling only the edges that
    should exist would let a new one through unnoticed, and a new edge into or out of
    DISABLED is precisely the change that would need an architectural decision.
    """
    assert LEGAL_ADMINISTRATIVE_TRANSITIONS == {
        None: frozenset({AdministrativeLifecycleState.REGISTERED}),
        AdministrativeLifecycleState.REGISTERED: frozenset(
            {AdministrativeLifecycleState.ACTIVE, AdministrativeLifecycleState.DISABLED}
        ),
        AdministrativeLifecycleState.ACTIVE: frozenset(
            {AdministrativeLifecycleState.DISABLED}
        ),
        AdministrativeLifecycleState.DISABLED: frozenset(),
    }


@pytest.mark.security_invariant
def test_disabled_is_terminal() -> None:
    """No target is reachable from DISABLED, including REGISTERED."""
    for target in AdministrativeLifecycleState:
        assert (
            is_legal_administrative_transition(
                AdministrativeLifecycleState.DISABLED, target
            )
            is False
        )


@pytest.mark.security_invariant
def test_registration_is_the_only_transition_from_no_state() -> None:
    """An agent cannot be activated into existence."""
    assert (
        is_legal_administrative_transition(
            None, AdministrativeLifecycleState.REGISTERED
        )
        is True
    )
    for target in (
        AdministrativeLifecycleState.ACTIVE,
        AdministrativeLifecycleState.DISABLED,
    ):
        assert is_legal_administrative_transition(None, target) is False


@pytest.mark.security_invariant
def test_an_unclassified_previous_state_is_not_transitionable() -> None:
    """Fail closed on a state the graph does not know, rather than raising.

    The same default F-09.A established for execution: an unknown state is not a
    permission. Raising would be a different outcome for the caller -- unavailable rather
    than refused -- and the two are not interchangeable (L.10).
    """
    assert (
        is_legal_administrative_transition(
            "QUARANTINED",  # type: ignore[arg-type]
            AdministrativeLifecycleState.ACTIVE,
        )
        is False
    )


def test_every_legal_edge_has_exactly_one_recorded_action() -> None:
    """The ledger action is derived from the pair, so the two tables must agree.

    A legal edge with no action could not be recorded; an action for an illegal edge
    would let the ledger describe a transition that cannot happen.
    """
    legal_edges = {
        (previous, new)
        for previous, targets in LEGAL_ADMINISTRATIVE_TRANSITIONS.items()
        for new in targets
    }
    assert set(ADMINISTRATIVE_TRANSITION_ACTIONS) == legal_edges


def test_disablement_is_recorded_as_disable_from_either_source_state() -> None:
    assert (
        ADMINISTRATIVE_TRANSITION_ACTIONS[
            (
                AdministrativeLifecycleState.REGISTERED,
                AdministrativeLifecycleState.DISABLED,
            )
        ]
        is AdministrativeAction.DISABLE
    )
    assert (
        ADMINISTRATIVE_TRANSITION_ACTIONS[
            (
                AdministrativeLifecycleState.ACTIVE,
                AdministrativeLifecycleState.DISABLED,
            )
        ]
        is AdministrativeAction.DISABLE
    )


@pytest.mark.security_invariant
def test_administrative_state_is_frozen() -> None:
    """Lifecycle state is replaced wholesale, never edited in place."""
    state = AgentAdministrativeState(
        agent_id="a",
        state=AdministrativeLifecycleState.ACTIVE,
        administrative_version=1,
    )
    with pytest.raises(ValidationError):
        state.state = AdministrativeLifecycleState.DISABLED  # type: ignore[misc]


def test_version_zero_is_not_a_representable_state() -> None:
    """Registration commits version 1, so 0 means "no record", never a stored state.

    Enforced by the model rather than by convention: if 0 were representable, a stored
    state and an absent one would again be indistinguishable -- the ambiguity AP.1
    removed from ``Agent.status``.
    """
    with pytest.raises(ValidationError):
        AgentAdministrativeState(
            agent_id="a",
            state=AdministrativeLifecycleState.REGISTERED,
            administrative_version=0,
        )


def test_an_actor_requires_both_a_type_and_an_identity() -> None:
    """Actor type and identity are never a single overloaded string (A.8)."""
    with pytest.raises(ValidationError):
        Actor(type="human", id="")
    with pytest.raises(ValidationError):
        Actor(type="not-a-type", id="x")  # type: ignore[arg-type]
