"""Two-plane lifecycle authorization and L.10 precedence (ADR-024 A.4, ADR-030 AP.9)."""

from datetime import datetime, timezone

import pytest

from app.models.agent_administrative import (
    AdministrativeLifecycleState,
    AgentAdministrativeState,
)
from app.models.agent_enforcement import AgentEnforcementState
from app.models.authorization_result import LifecycleRefusalCode
from app.policy.lifecycle_authorization import (
    REFUSAL_PRECEDENCE,
    evaluate_lifecycle_authorization,
    failing_lifecycle_conditions,
)

SUSPENDED_AT = datetime(2026, 6, 1, tzinfo=timezone.utc)


def admin(state: AdministrativeLifecycleState) -> AgentAdministrativeState:
    return AgentAdministrativeState(
        agent_id="a", state=state, administrative_version=1
    )


def enforcement(*, suspended: bool) -> AgentEnforcementState:
    return AgentEnforcementState(
        agent_id="a", epoch=1, suspended_at=SUSPENDED_AT if suspended else None
    )


# Every combination of the two planes' readings. Written as a cross-product rather than a
# set of chosen cases, because the defect this guards against is a combination nobody
# thought to try -- which is how REGISTERED stayed executable.
#
# admin_state: None means no record; "unavailable" means the repository could not answer.
CASES = [
    # (admin, admin_available, enf, enf_available, expected)
    ("unavailable", False, "none", True, LifecycleRefusalCode.ADMINISTRATIVE_STATE_UNAVAILABLE),
    ("unavailable", False, "unavailable", False, LifecycleRefusalCode.ADMINISTRATIVE_STATE_UNAVAILABLE),
    ("unavailable", False, "suspended", True, LifecycleRefusalCode.ADMINISTRATIVE_STATE_UNAVAILABLE),
    ("none", True, "none", True, LifecycleRefusalCode.ADMINISTRATIVE_STATE_UNAVAILABLE),
    ("none", True, "unavailable", False, LifecycleRefusalCode.ADMINISTRATIVE_STATE_UNAVAILABLE),
    ("none", True, "suspended", True, LifecycleRefusalCode.ADMINISTRATIVE_STATE_UNAVAILABLE),
    ("DISABLED", True, "unavailable", False, LifecycleRefusalCode.ENFORCEMENT_STATE_UNAVAILABLE),
    ("REGISTERED", True, "unavailable", False, LifecycleRefusalCode.ENFORCEMENT_STATE_UNAVAILABLE),
    ("ACTIVE", True, "unavailable", False, LifecycleRefusalCode.ENFORCEMENT_STATE_UNAVAILABLE),
    ("DISABLED", True, "none", True, LifecycleRefusalCode.AGENT_DISABLED),
    ("DISABLED", True, "not_suspended", True, LifecycleRefusalCode.AGENT_DISABLED),
    ("DISABLED", True, "suspended", True, LifecycleRefusalCode.AGENT_DISABLED),
    ("REGISTERED", True, "none", True, LifecycleRefusalCode.AGENT_NOT_ACTIVE),
    ("REGISTERED", True, "not_suspended", True, LifecycleRefusalCode.AGENT_NOT_ACTIVE),
    ("REGISTERED", True, "suspended", True, LifecycleRefusalCode.AGENT_NOT_ACTIVE),
    ("ACTIVE", True, "suspended", True, LifecycleRefusalCode.AGENT_SUSPENDED),
    # The only permitted combinations: administratively ACTIVE and not contained.
    ("ACTIVE", True, "none", True, None),
    ("ACTIVE", True, "not_suspended", True, None),
]


def _build(admin_state: str, enf_state: str):
    administrative = None if admin_state in ("unavailable", "none") else admin(
        AdministrativeLifecycleState(admin_state)
    )
    enf = None
    if enf_state == "suspended":
        enf = enforcement(suspended=True)
    elif enf_state == "not_suspended":
        enf = enforcement(suspended=False)
    return administrative, enf


@pytest.mark.security_invariant
@pytest.mark.parametrize(
    ("admin_state", "admin_available", "enf_state", "enf_available", "expected"), CASES
)
def test_the_lifecycle_cross_product(
    admin_state, admin_available, enf_state, enf_available, expected
) -> None:
    """Both planes, every combination, including simultaneous failures."""
    administrative, enf = _build(admin_state, enf_state)

    assert (
        evaluate_lifecycle_authorization(
            administrative=administrative,
            administrative_available=admin_available,
            enforcement=enf,
            enforcement_available=enf_available,
        )
        is expected
    )


@pytest.mark.security_invariant
def test_only_administratively_active_and_uncontained_permits_execution() -> None:
    """Stated independently of the table: exactly two readings permit execution.

    The table asserts each case; this asserts the *shape* -- that permission is granted
    by the presence of both conditions rather than by the absence of a deny condition. A
    new lifecycle state added later is non-executable by this test without anyone
    extending the table.
    """
    permitted = set()
    for state in AdministrativeLifecycleState:
        for suspended in (True, False):
            if (
                evaluate_lifecycle_authorization(
                    administrative=admin(state),
                    administrative_available=True,
                    enforcement=enforcement(suspended=suspended),
                    enforcement_available=True,
                )
                is None
            ):
                permitted.add((state, suspended))

    assert permitted == {(AdministrativeLifecycleState.ACTIVE, False)}


@pytest.mark.security_invariant
def test_precedence_does_not_depend_on_evaluation_order() -> None:
    """AP.9: precedence is semantic.

    The failure mode this closes is an implementation that returns the first *failing
    check* instead of the most significant one. Such an implementation satisfies the
    vocabulary and reports the wrong code whenever two conditions fail together, which is
    exactly when an operator most needs the right one.

    Asserted by taking every failing set the evaluator can produce and checking the
    selection against the declared order, rather than against the order the conditions
    happen to be computed in.
    """
    for admin_state, admin_av, enf_state, enf_av, expected in CASES:
        administrative, enf = _build(admin_state, enf_state)
        failing = failing_lifecycle_conditions(
            administrative=administrative,
            administrative_available=admin_av,
            enforcement=enf,
            enforcement_available=enf_av,
        )
        if not failing:
            assert expected is None
            continue
        most_significant = next(c for c in REFUSAL_PRECEDENCE if c in failing)
        assert most_significant is expected


@pytest.mark.security_invariant
def test_simultaneous_failures_surface_the_more_significant_code() -> None:
    """The specific case a short-circuiting implementation gets wrong.

    A disabled agent whose enforcement plane is also unreachable must report
    ENFORCEMENT_STATE_UNAVAILABLE, not AGENT_DISABLED: inability to establish state
    outranks a known state, because a known state asserts something the platform cannot
    currently verify.
    """
    both = failing_lifecycle_conditions(
        administrative=admin(AdministrativeLifecycleState.DISABLED),
        administrative_available=True,
        enforcement=None,
        enforcement_available=False,
    )
    assert both == {
        LifecycleRefusalCode.AGENT_DISABLED,
        LifecycleRefusalCode.ENFORCEMENT_STATE_UNAVAILABLE,
    }
    assert (
        evaluate_lifecycle_authorization(
            administrative=admin(AdministrativeLifecycleState.DISABLED),
            administrative_available=True,
            enforcement=None,
            enforcement_available=False,
        )
        is LifecycleRefusalCode.ENFORCEMENT_STATE_UNAVAILABLE
    )


@pytest.mark.security_invariant
def test_the_precedence_order_covers_every_refusal_code() -> None:
    """A code outside the order would have no defined significance.

    Guards the omission rather than the order: a sixth code added without a position
    would fall through the scan, and the evaluator's fallback would report something
    else entirely.
    """
    assert set(REFUSAL_PRECEDENCE) == set(LifecycleRefusalCode)
    assert len(REFUSAL_PRECEDENCE) == len(LifecycleRefusalCode)


@pytest.mark.security_invariant
def test_a_missing_enforcement_record_is_not_unavailable() -> None:
    """The two planes' absences mean different things, deliberately.

    No administrative record means the state cannot be established (L.3). No enforcement
    record means the agent has never been contained, which is a known state: not
    suspended. Treating enforcement absence as unavailable would make every
    never-suspended agent non-executable -- a total outage dressed as fail-closed.
    """
    assert (
        evaluate_lifecycle_authorization(
            administrative=admin(AdministrativeLifecycleState.ACTIVE),
            administrative_available=True,
            enforcement=None,
            enforcement_available=True,
        )
        is None
    )


@pytest.mark.security_invariant
def test_an_unclassified_administrative_state_is_not_executable() -> None:
    """A state nobody classified must refuse, not fall through to permitted.

    Found by mutation: deleting this branch left every other test green, because the
    refusal mapping covers REGISTERED and DISABLED and ACTIVE is the only value left, so
    with today's enum the branch is unreachable. Unreachable is not the same as
    unnecessary -- it becomes reachable the moment a state is added, and the failure mode
    is that the new state is silently executable.

    This is the defect F-09.A removed from the execution gate, one layer down. Built via
    ``model_construct`` to bypass enum validation, which is the only way to present the
    evaluator with a state the enum does not contain.
    """
    unclassified = AgentAdministrativeState.model_construct(
        agent_id="a",
        state="QUARANTINED",  # type: ignore[arg-type]
        administrative_version=1,
    )

    assert (
        evaluate_lifecycle_authorization(
            administrative=unclassified,
            administrative_available=True,
            enforcement=enforcement(suspended=False),
            enforcement_available=True,
        )
        is LifecycleRefusalCode.AGENT_NOT_ACTIVE
    )


@pytest.mark.security_invariant
def test_every_administrative_state_is_classified_as_executable_or_refused() -> None:
    """No member of the enum may be left unconsidered by the evaluator.

    Guards the omission rather than any one state, so a state added later fails here
    instead of inheriting whichever branch it happens to reach.
    """
    for state in AdministrativeLifecycleState:
        outcome = evaluate_lifecycle_authorization(
            administrative=admin(state),
            administrative_available=True,
            enforcement=enforcement(suspended=False),
            enforcement_available=True,
        )
        if state is AdministrativeLifecycleState.ACTIVE:
            assert outcome is None
        else:
            assert outcome is not None
