"""Administrative lifecycle state and history for an agent (ADR-024 F-09, ADR-030 AP.*).

Two independently authoritative planes govern whether an agent may execute. This module
models the **administrative** one; ``agent_enforcement`` models the enforcement one.

    Administrative   REGISTERED / ACTIVE / DISABLED   versioned by administrative_version
    Enforcement      NOT_SUSPENDED / SUSPENDED        versioned by epoch

Neither plane may reuse the other's version namespace, and the two values are never
compared or substituted (ADR-030 AP.2). They count different things at different rates.

``AgentAdministrativeState``
    The agent's *current* administrative state and the version that serialises changes
    to it. Replaced wholesale on every committed transition.

``AdministrativeTransition``
    One immutable ledger record of a state change. The ledger is **both** transition
    history and authoritative lifecycle evidence: a committed transition is recorded
    once, here, and is never duplicated into ``AuditEvent`` (ADR-024 A.8, AP.6).

This record — not ``Agent.status`` — is the authority. ``Agent.status`` is a computed
projection over both planes and is never persisted (AP.1).
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AdministrativeLifecycleState(str, Enum):
    """The administrative lifecycle states (ADR-024 A.3).

    Distinct from ``AgentStatus``, which is the projection vocabulary and additionally
    carries ``SUSPENDED`` from the enforcement plane. ``SUSPENDED`` is deliberately
    absent here: containment is not an administrative state, and representing it would
    let one plane express the other's posture.
    """

    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class AdministrativeAction(str, Enum):
    """The operations that change administrative lifecycle state."""

    REGISTER = "REGISTER"
    ACTIVATE = "ACTIVATE"
    DISABLE = "DISABLE"


class ActorType(str, Enum):
    """Controlled actor types (ADR-024 A.8).

    Actor type and identity are never a single overloaded string: "system" and a user
    named "system" must not be indistinguishable in evidence.
    """

    HUMAN = "human"
    SYSTEM = "system"
    RUNTIME = "runtime"


class Actor(BaseModel):
    """Who performed an administrative operation, structured (ADR-024 A.8)."""

    model_config = ConfigDict(frozen=True)

    type: ActorType
    id: str = Field(min_length=1)


# The legal administrative transition graph (ADR-024 A.3, ADR-030 AP.5). Defined once so
# the service, the repositories and the contract suite cannot disagree about it.
#
# ``None`` is the pre-registration state: an agent with no administrative record has no
# establishable state, which is reported as ADMINISTRATIVE_STATE_UNAVAILABLE and is never
# interpreted as REGISTERED (ADR-030 L.3).
LEGAL_ADMINISTRATIVE_TRANSITIONS: dict[
    AdministrativeLifecycleState | None, frozenset[AdministrativeLifecycleState]
] = {
    None: frozenset({AdministrativeLifecycleState.REGISTERED}),
    AdministrativeLifecycleState.REGISTERED: frozenset(
        {AdministrativeLifecycleState.ACTIVE, AdministrativeLifecycleState.DISABLED}
    ),
    AdministrativeLifecycleState.ACTIVE: frozenset(
        {AdministrativeLifecycleState.DISABLED}
    ),
    # DISABLED is terminal. A future re-enable would be a separately defined, separately
    # authorized transition; reinstatement is never that transition (ADR-024 A.3).
    AdministrativeLifecycleState.DISABLED: frozenset(),
}

# The action each transition is recorded under. Derived from the pair rather than
# supplied by the caller, so the ledger cannot describe a transition as an operation it
# was not.
ADMINISTRATIVE_TRANSITION_ACTIONS: dict[
    tuple[AdministrativeLifecycleState | None, AdministrativeLifecycleState],
    AdministrativeAction,
] = {
    (None, AdministrativeLifecycleState.REGISTERED): AdministrativeAction.REGISTER,
    (
        AdministrativeLifecycleState.REGISTERED,
        AdministrativeLifecycleState.ACTIVE,
    ): AdministrativeAction.ACTIVATE,
    (
        AdministrativeLifecycleState.REGISTERED,
        AdministrativeLifecycleState.DISABLED,
    ): AdministrativeAction.DISABLE,
    (
        AdministrativeLifecycleState.ACTIVE,
        AdministrativeLifecycleState.DISABLED,
    ): AdministrativeAction.DISABLE,
}


def is_legal_administrative_transition(
    previous: AdministrativeLifecycleState | None,
    new: AdministrativeLifecycleState,
) -> bool:
    """Return whether this administrative transition is permitted (AP.5).

    An unknown ``previous`` yields False rather than raising: a state the graph does not
    classify is non-transitionable, the same fail-closed default F-09.A established for
    execution.
    """
    return new in LEGAL_ADMINISTRATIVE_TRANSITIONS.get(previous, frozenset())


class AdministrativeTransition(BaseModel):
    """An immutable ledger record of one administrative lifecycle change (ADR-024 A.8).

    Carries the version on **both** sides of the change. The enforcement ledger records
    only the epoch after, which leaves a reader unable to tell an ordinary step from one
    that skipped; recording both makes the ledger self-checking.
    """

    model_config = ConfigDict(frozen=True)

    transition_id: str
    agent_id: str
    action: AdministrativeAction
    actor: Actor
    reason: str
    # None only for REGISTER: before registration there is no administrative state, and
    # naming one would assert a history that did not happen.
    previous_state: AdministrativeLifecycleState | None = None
    new_state: AdministrativeLifecycleState
    administrative_version_before: int = Field(ge=0)
    administrative_version_after: int = Field(ge=1)
    # Mandatory. System-initiated operations generate one per transition (ADR-024 A.8);
    # there is no unattributed administrative transition.
    correlation_id: str = Field(min_length=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentAdministrativeState(BaseModel):
    """The current administrative lifecycle state of one agent.

    Invariants:
    - Authoritative State: this record, not ``Agent.status``, is the authority for
      REGISTERED / ACTIVE / DISABLED (AP.1). ``Agent.status`` is a computed projection
      over this plane and the enforcement plane, and is never persisted.
    - Authoritative Version: ``administrative_version`` is the persisted monotonic
      concurrency version. Registration commits version 1; every committed transition
      thereafter increments it by exactly +1.
    - Namespace Independence: ``administrative_version`` is never compared with,
      substituted for, or validated against ``AgentEnforcementState.epoch`` (AP.2).
    - Absence Is Not A State: no record means the administrative state cannot be
      established. That is ``ADMINISTRATIVE_STATE_UNAVAILABLE``, never ``REGISTERED``
      (ADR-030 L.3, L.10).
    """

    model_config = ConfigDict(frozen=True)

    agent_id: str
    state: AdministrativeLifecycleState
    administrative_version: int = Field(
        ge=1,
        description=(
            "Monotonic concurrency version. Registration commits 1; every committed "
            "transition thereafter increments by exactly +1. Never compared with epoch."
        ),
    )
    last_transition_at: datetime | None = None
