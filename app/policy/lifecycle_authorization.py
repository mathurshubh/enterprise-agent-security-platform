"""Lifecycle execution authorization across both planes (ADR-024 A.4, ADR-030 AP.9/L.10).

An agent may obtain execution authority only when its authoritative administrative state
is ``ACTIVE`` **and** its authoritative enforcement state is not suspended. Each condition
is evaluated independently against its own authority and fails closed if it cannot be
established.

Execution is granted by the presence of both conditions, never inferred from the absence
of a deny condition. Because each fails closed independently, the two planes may commit
in either order without opening an executable window.

Deterministic and total: a pure function of the two plane readings, with no clock, no I/O
and no LLM involvement.
"""

from app.models.agent_administrative import (
    AdministrativeLifecycleState,
    AgentAdministrativeState,
)
from app.models.agent_enforcement import AgentEnforcementState
from app.models.authorization_result import LifecycleRefusalCode

# ADR-030 L.10. Ordered most to least significant: when several conditions fail at once,
# the first of these present is the one surfaced.
#
# Held as data and applied by scanning this tuple, rather than as a chain of early
# returns. Evaluation order and precedence are then the same thing by construction, which
# is what AP.9 requires: an implementation that returns the first *failing check* instead
# satisfies the vocabulary and still reports the wrong code whenever two conditions fail
# together.
REFUSAL_PRECEDENCE: tuple[LifecycleRefusalCode, ...] = (
    LifecycleRefusalCode.ADMINISTRATIVE_STATE_UNAVAILABLE,
    LifecycleRefusalCode.ENFORCEMENT_STATE_UNAVAILABLE,
    LifecycleRefusalCode.AGENT_DISABLED,
    LifecycleRefusalCode.AGENT_NOT_ACTIVE,
    LifecycleRefusalCode.AGENT_SUSPENDED,
)

_ADMINISTRATIVE_REFUSALS: dict[AdministrativeLifecycleState, LifecycleRefusalCode] = {
    AdministrativeLifecycleState.REGISTERED: LifecycleRefusalCode.AGENT_NOT_ACTIVE,
    AdministrativeLifecycleState.DISABLED: LifecycleRefusalCode.AGENT_DISABLED,
}


def failing_lifecycle_conditions(
    *,
    administrative: AgentAdministrativeState | None,
    administrative_available: bool,
    enforcement: AgentEnforcementState | None,
    enforcement_available: bool,
) -> set[LifecycleRefusalCode]:
    """Return every lifecycle condition that currently forbids execution.

    Returns the whole set rather than the first failure, so the caller selects by
    precedence rather than by the order these happen to be computed.

    The two planes' "missing record" cases are deliberately asymmetric, because they mean
    different things:

    - **No administrative record** is an agent whose administrative state cannot be
      established. L.3 is explicit that this is ``ADMINISTRATIVE_STATE_UNAVAILABLE`` and
      never ``REGISTERED``.
    - **No enforcement record** is an agent that has never been contained, which is a
      known state: not suspended. Treating it as unavailable would make every
      never-suspended agent non-executable.
    """
    failing: set[LifecycleRefusalCode] = set()

    if not administrative_available or administrative is None:
        failing.add(LifecycleRefusalCode.ADMINISTRATIVE_STATE_UNAVAILABLE)
    else:
        refusal = _ADMINISTRATIVE_REFUSALS.get(administrative.state)
        if refusal is not None:
            failing.add(refusal)
        elif administrative.state is not AdministrativeLifecycleState.ACTIVE:
            # A state the mapping does not classify is non-executable. Only ACTIVE
            # permits execution, so anything unrecognised refuses rather than falling
            # through -- the fail-closed default F-09.A established.
            failing.add(LifecycleRefusalCode.AGENT_NOT_ACTIVE)

    if not enforcement_available:
        failing.add(LifecycleRefusalCode.ENFORCEMENT_STATE_UNAVAILABLE)
    elif enforcement is not None and enforcement.suspended_at is not None:
        failing.add(LifecycleRefusalCode.AGENT_SUSPENDED)

    return failing


def evaluate_lifecycle_authorization(
    *,
    administrative: AgentAdministrativeState | None,
    administrative_available: bool,
    enforcement: AgentEnforcementState | None,
    enforcement_available: bool,
) -> LifecycleRefusalCode | None:
    """Return the primary refusal code, or None when both planes permit execution.

    The code returned is the most significant failing condition under L.10, independent of
    the order in which the conditions were computed.
    """
    failing = failing_lifecycle_conditions(
        administrative=administrative,
        administrative_available=administrative_available,
        enforcement=enforcement,
        enforcement_available=enforcement_available,
    )
    if not failing:
        return None

    for code in REFUSAL_PRECEDENCE:
        if code in failing:
            return code

    # Unreachable while REFUSAL_PRECEDENCE covers LifecycleRefusalCode, which a test
    # asserts. Refusing rather than permitting keeps an unclassified future code
    # fail-closed instead of silently executable.
    return LifecycleRefusalCode.AGENT_NOT_ACTIVE
