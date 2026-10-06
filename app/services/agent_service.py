from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from app.models.agent import Agent, AgentStatus
from app.models.agent_administrative import (
    ADMINISTRATIVE_TRANSITION_ACTIONS,
    Actor,
    ActorType,
    AdministrativeLifecycleState,
    AdministrativeTransition,
    AgentAdministrativeState,
    is_legal_administrative_transition,
)
from app.models.agent_enforcement import (
    AgentEnforcementState,
    EnforcementAction,
    EnforcementTransition,
    EnforcementTrigger,
)
from app.models.watermark import BaselineWatermark
from app.repositories.interfaces.administrative_state_repository import (
    AdministrativeStateRepository,
)
from app.repositories.interfaces.agent_repository import AgentRepository
from app.repositories.interfaces.enforcement_state_repository import (
    EnforcementStateRepository,
    EnforcementStateUnavailableError,
)

# Suspension is written by the deterministic runtime pipeline, never by an operator
# request. Reinstatement is the opposite: it always names the operator who performed it.
RUNTIME_ACTOR = "runtime"

# Reserved system identifiers for programmatic lifecycle operations (ADR-024 A.8).
#
# Defaulting the actor is defensible here in a way it would not be for a decision input:
# the actor is evidence attribution, nothing authorizes on it, and "system" is the
# truthful answer for a registration no human requested. A human-initiated registration
# through the management plane passes its own actor. This is deliberately not the shape of
# a permissive default on a security predicate, which F-02 corrected on capability digests
# and F-09.A corrected on the execution gate.
SYSTEM_REGISTRATION_ACTOR = Actor(type=ActorType.SYSTEM, id="system")
BOOTSTRAP_ACTOR = Actor(type=ActorType.SYSTEM, id="bootstrap")
SCENARIO_RUNTIME_ACTOR = Actor(type=ActorType.SYSTEM, id="scenario-runtime")


class AgentAlreadyExistsError(Exception):
    """Raised when attempting to register an existing agent."""


class AgentNotFoundError(Exception):
    """Raised when an agent cannot be found."""


class AgentNotSuspendedError(Exception):
    """Raised when reinstating an agent that is not suspended."""


class EnforcementConcurrencyError(Exception):
    """Raised when an enforcement state transition fails due to concurrent modification (CAS epoch mismatch)."""


class AdministrativeConcurrencyError(Exception):
    """Raised when an administrative transition loses a compare-and-set race.

    Separate from the enforcement equivalent because the two planes have separate version
    namespaces, and a caller retrying one must not be told the other moved (AP.2).
    """


class IllegalAdministrativeTransitionError(Exception):
    """Raised when a requested administrative transition is not in the legal graph (AP.5)."""


class AgentService:
    """Registry of agents and the authority for their enforcement state (M2b, PR #181).

    Enforcement state is monotonic from the runtime's perspective: the pipeline may
    suspend an agent, and only an explicit, attributed reinstatement returns it to
    service. No other method on this service produces that transition.

    In PR #181, AgentRepository and EnforcementStateRepository are the sole authoritative
    state sources (no internal dicts).
    """

    def __init__(
        self,
        agent_repository: AgentRepository,
        enforcement_repository: EnforcementStateRepository,
        administrative_repository: AdministrativeStateRepository,
    ) -> None:
        self._lock = RLock()
        self._agent_repository = agent_repository
        self._enforcement_repository = enforcement_repository
        # Required, not optional. An absent administrative authority would make every
        # agent ADMINISTRATIVE_STATE_UNAVAILABLE once the planes are read for
        # authorization, and an optional security dependency defaults to whatever the
        # caller forgot -- the shape F-02 corrected on capability digests.
        self._administrative_repository = administrative_repository

    @property
    def agent_repository(self) -> AgentRepository:
        """Injected AgentRepository protocol instance."""
        return self._agent_repository

    @property
    def enforcement_repository(self) -> EnforcementStateRepository:
        """Injected EnforcementStateRepository protocol instance."""
        return self._enforcement_repository

    @property
    def administrative_repository(self) -> AdministrativeStateRepository:
        """Injected AdministrativeStateRepository protocol instance."""
        return self._administrative_repository

    def register_agent(
        self,
        agent: Agent,
        *,
        actor: Actor = SYSTEM_REGISTRATION_ACTOR,
        correlation_id: str | None = None,
    ) -> Agent:
        """Register an agent: it becomes known to the platform and holds no authority.

        Registration is the first administrative transition and yields ``REGISTERED``
        (ADR-024 A.3, A.10 as refined by AP.3). It grants nothing: a registered agent is
        not executable, and entering service requires a separate, explicitly authorized
        activation.

        The administrative record is written before the agent record. If the second write
        fails, the agent is unreachable through this service -- ``get_agent`` raises
        ``AgentNotFoundError`` -- so the orphan is inert. The reverse order would leave an
        agent that exists with no establishable administrative state, which every
        lifecycle read would then have to treat as unavailable.
        """
        with self._lock:
            existing = self._agent_repository.get(agent.agent_id)
            if existing is not None:
                raise AgentAlreadyExistsError(
                    f"Agent '{agent.agent_id}' already exists"
                )

            self._administrative_transition(
                agent_id=agent.agent_id,
                new_state=AdministrativeLifecycleState.REGISTERED,
                actor=actor,
                reason="Agent registered",
                correlation_id=correlation_id,
            )

            self._agent_repository.save(agent)
            return agent

    def activate_agent(
        self,
        agent_id: str,
        *,
        actor: Actor,
        reason: str = "Agent activated",
        correlation_id: str | None = None,
    ) -> AgentAdministrativeState:
        """Put a registered agent into service (ADR-024 A.3).

        The only transition that makes an agent administratively executable, and it is
        always explicit: registration and activation are distinct lifecycle events even
        when performed consecutively, so each produces its own ledger entry.

        Activation is not a grant-freshness event (A.7) and does not touch the enforcement
        plane. An agent activated while contained stays contained.
        """
        with self._lock:
            self.get_agent(agent_id)
            return self._administrative_transition(
                agent_id=agent_id,
                new_state=AdministrativeLifecycleState.ACTIVE,
                actor=actor,
                reason=reason,
                correlation_id=correlation_id,
            )

    def disable_agent(
        self,
        agent_id: str,
        *,
        actor: Actor,
        reason: str = "Agent disabled",
        correlation_id: str | None = None,
    ) -> AgentAdministrativeState:
        """Remove an agent from service permanently (ADR-024 A.3).

        Terminal: no administrative transition leaves ``DISABLED``. A future re-enable
        would be a separately defined, separately authorized transition, and reinstatement
        is never that transition.

        Disablement removes execution authority, so it closes issuance on the
        administrative plane. That closure is the administrative plane's alone: a later
        reinstatement clears the enforcement plane's closure and leaves this one standing
        (A.7), which is what keeps a disabled agent non-executable through any enforcement
        transition.
        """
        with self._lock:
            self.get_agent(agent_id)
            return self._administrative_transition(
                agent_id=agent_id,
                new_state=AdministrativeLifecycleState.DISABLED,
                actor=actor,
                reason=reason,
                correlation_id=correlation_id,
            )

    def register_and_activate_agent(
        self,
        agent: Agent,
        *,
        actor: Actor,
        correlation_id: str | None = None,
    ) -> Agent:
        """Register an agent and put it into service, as two distinct transitions.

        ADR-024 A.3 requires registration and activation to be distinct lifecycle events
        "even when performed consecutively". This performs both and produces **two**
        ledger entries, which is what makes them distinct; it is a convenience for callers
        that legitimately do both at once, not a single combined transition.

        Used by system-initiated paths -- bootstrap and the scenario runtime -- which have
        no operator to perform the activation separately. An operator-driven registration
        activates through its own authorized request.
        """
        with self._lock:
            registered = self.register_agent(
                agent, actor=actor, correlation_id=correlation_id
            )
            self.activate_agent(
                agent.agent_id,
                actor=actor,
                reason="Activated on registration by a system actor",
                correlation_id=correlation_id,
            )
            return registered

    def administrative_state(self, agent_id: str) -> AgentAdministrativeState | None:
        """Return the agent's authoritative administrative state, or None if unestablishable.

        None is not ``REGISTERED``. L.10 surfaces it as
        ``ADMINISTRATIVE_STATE_UNAVAILABLE``, which is not a lifecycle state.
        """
        with self._lock:
            return self._administrative_repository.get_state(agent_id)

    def list_administrative_transitions(
        self, agent_id: str | None = None
    ) -> list[AdministrativeTransition]:
        """Return the administrative ledger, which is authoritative lifecycle evidence."""
        with self._lock:
            return self._administrative_repository.list_transitions(agent_id)

    def _administrative_transition(
        self,
        *,
        agent_id: str,
        new_state: AdministrativeLifecycleState,
        actor: Actor,
        reason: str,
        correlation_id: str | None,
    ) -> AgentAdministrativeState:
        """Apply one administrative transition under compare-and-set.

        The legality check happens here as well as in the repository, and that duplication
        is deliberate: the service can refuse with a domain error naming the states, while
        the repository refuses anything that reaches it from any caller. The repository is
        the boundary that commits, so it is the one that must not be bypassable.
        """
        current = self._administrative_repository.get_state(agent_id)
        previous_state = current.state if current else None
        expected_version = current.administrative_version if current else 0

        if not is_legal_administrative_transition(previous_state, new_state):
            raise IllegalAdministrativeTransitionError(
                f"Illegal administrative transition for agent '{agent_id}': "
                f"{previous_state.value if previous_state else 'none'} -> "
                f"{new_state.value}."
            )

        now = datetime.now(timezone.utc)
        next_version = expected_version + 1
        transition = AdministrativeTransition(
            transition_id=f"admin-transition-{uuid4()}",
            agent_id=agent_id,
            action=ADMINISTRATIVE_TRANSITION_ACTIONS[(previous_state, new_state)],
            actor=actor,
            reason=reason,
            previous_state=previous_state,
            new_state=new_state,
            administrative_version_before=expected_version,
            administrative_version_after=next_version,
            correlation_id=correlation_id or f"corr-{uuid4()}",
            occurred_at=now,
        )
        updated = AgentAdministrativeState(
            agent_id=agent_id,
            state=new_state,
            administrative_version=next_version,
            last_transition_at=now,
        )

        committed = self._administrative_repository.record_transition(
            transition,
            updated,
            expected_version=expected_version,
        )
        if not committed:
            raise AdministrativeConcurrencyError(
                f"Concurrent administrative modification for agent '{agent_id}' "
                f"(expected administrative version {expected_version})"
            )
        return updated

    def get_agent(self, agent_id: str) -> Agent:
        with self._lock:
            agent = self._agent_repository.get(agent_id)
            if agent is None:
                raise AgentNotFoundError(f"Agent '{agent_id}' not found")

            # Dynamic enforcement posture projection (fail-closed)
            if agent.status != AgentStatus.DISABLED:
                try:
                    enf_state = self._enforcement_repository.get_state(agent_id)
                except EnforcementStateUnavailableError:
                    raise
                except Exception as exc:
                    raise EnforcementStateUnavailableError(
                        f"Enforcement state repository unavailable for agent '{agent_id}': {exc}"
                    ) from exc

                if enf_state is not None and enf_state.suspended_at is not None:
                    agent = agent.model_copy(update={"status": AgentStatus.SUSPENDED})

            return agent

    def list_agents(self) -> list[Agent]:
        with self._lock:
            agents = self._agent_repository.list()
            projected = []
            for agent in agents:
                if agent.status != AgentStatus.DISABLED:
                    try:
                        enf_state = self._enforcement_repository.get_state(agent.agent_id)
                    except EnforcementStateUnavailableError:
                        raise
                    except Exception as exc:
                        raise EnforcementStateUnavailableError(
                            f"Enforcement state repository unavailable for agent '{agent.agent_id}': {exc}"
                        ) from exc

                    if enf_state is not None and enf_state.suspended_at is not None:
                        agent = agent.model_copy(
                            update={"status": AgentStatus.SUSPENDED}
                        )
                projected.append(agent)
            return projected

    def suspend_agent(
        self,
        agent_id: str,
        *,
        reason: str,
        trigger: EnforcementTrigger | None = None,
    ) -> Agent:
        """Suspend an agent, recording why and what triggered it.

        Idempotent: an agent that is already suspended is returned unchanged and adds
        no second transition. A ``DISABLED`` agent is left alone, since that is the
        stronger administrative state.
        """
        with self._lock:
            agent = self.get_agent(agent_id)

            if agent.status in {AgentStatus.SUSPENDED, AgentStatus.DISABLED}:
                return agent

            return self._transition(
                agent=agent,
                new_status=AgentStatus.SUSPENDED,
                action=EnforcementAction.SUSPEND,
                actor=RUNTIME_ACTOR,
                reason=reason,
                trigger=trigger,
            )

    def reinstate_agent(
        self,
        agent_id: str,
        *,
        actor: str,
        reason: str,
        watermark: BaselineWatermark | None = None,
    ) -> Agent:
        """Return a suspended agent to active status (recovery path).

        Reinstatement establishes a new enforcement baseline: findings accepted before
        this moment remain in the evidence repository for audit and attribution, but no
        longer drive automated enforcement.

        Raises:
            AgentNotFoundError: the agent is not registered.
            AgentNotSuspendedError: the agent is not currently suspended.
            ValueError: the reinstatement is not attributed to an actor and a reason.
        """
        with self._lock:
            agent = self.get_agent(agent_id)

            if not actor.strip():
                raise ValueError("Reinstatement requires an actor")
            if not reason.strip():
                raise ValueError("Reinstatement requires a reason")

            if agent.status != AgentStatus.SUSPENDED:
                raise AgentNotSuspendedError(f"Agent '{agent_id}' is not suspended")

            return self._transition(
                agent=agent,
                new_status=AgentStatus.ACTIVE,
                action=EnforcementAction.REINSTATE,
                actor=actor,
                reason=reason,
                trigger=None,
                watermark=watermark,
            )

    def get_current_baseline(self, agent_id: str) -> BaselineWatermark:
        """Return the current enforcement baseline watermark for an agent (B-10).

        Reads the stored enforcement_baseline_at and both namespace watermarks.
        Never derives or recomputes a new baseline from findings.
        """
        with self._lock:
            state = self.get_enforcement_state(agent_id)
            return BaselineWatermark(
                agent_id=agent_id,
                baseline_at=state.enforcement_baseline_at,
                baseline_evidence_sequence=state.baseline_evidence_sequence,
                baseline_agent_sequence=state.baseline_agent_sequence,
            )

    def get_enforcement_state(self, agent_id: str) -> AgentEnforcementState:
        """Return the agent's current enforcement state."""
        with self._lock:
            self.get_agent(agent_id)
            state = self._enforcement_repository.get_state(agent_id)
            if state is None:
                return AgentEnforcementState(agent_id=agent_id)
            return state

    def list_transitions(
        self,
        agent_id: str | None = None,
    ) -> list[EnforcementTransition]:
        """Return recorded enforcement transitions in chronological order."""
        with self._lock:
            return self._enforcement_repository.list_transitions(agent_id)

    def enforcement_epoch(
        self,
        agent_id: str,
        *,
        as_of: datetime,
    ) -> int:
        """Return how many times this agent had been reinstated by ``as_of``."""
        with self._lock:
            return self._enforcement_repository.get_epoch(agent_id, as_of=as_of)

    def _transition(
        self,
        agent: Agent,
        new_status: AgentStatus,
        action: EnforcementAction,
        actor: str,
        reason: str,
        trigger: EnforcementTrigger | None,
        watermark: BaselineWatermark | None = None,
    ) -> Agent:
        """Apply one enforcement transition under the service lock via CAS and repository persistence."""
        # Administrative DISABLED is a terminal/non-executable posture.
        # A dynamic transition must never create enforcement state for a DISABLED agent.
        if agent.status == AgentStatus.DISABLED:
            return agent

        now = datetime.now(timezone.utc)

        state = self._enforcement_repository.get_state(agent.agent_id)
        if state is None:
            state = AgentEnforcementState(agent_id=agent.agent_id)

        expected_epoch = state.epoch
        next_epoch = expected_epoch + 1

        if action == EnforcementAction.SUSPEND:
            # ``recovery_generation`` is deliberately absent from this update. It advances
            # only on a committed REINSTATE (ADR-030 amendment DR-8(c)); ``epoch`` advances
            # on every transition, and conflating the two is the namespace substitution the
            # architecture principles prohibit.
            new_state = state.model_copy(
                update={
                    "epoch": next_epoch,
                    "suspended_at": now,
                    "suspension_reason": reason,
                    "last_transition_at": now,
                }
            )
        else:
            baseline_at = (
                watermark.baseline_at
                if watermark and watermark.baseline_at is not None
                else now
            )
            baseline_evidence_seq = (
                watermark.baseline_evidence_sequence if watermark else 0
            )
            baseline_agent_seq = (
                watermark.baseline_agent_sequence if watermark else 0
            )
            new_state = state.model_copy(
                update={
                    "epoch": next_epoch,
                    "suspended_at": None,
                    "suspension_reason": None,
                    "enforcement_baseline_at": baseline_at,
                    "baseline_evidence_sequence": baseline_evidence_seq,
                    "baseline_agent_sequence": baseline_agent_seq,
                    # The sole mutator, by exactly +1, committed in the same
                    # compare-and-set that records the reinstatement (DR-8(c)).
                    "recovery_generation": state.recovery_generation + 1,
                    "last_transition_at": now,
                }
            )

        transition = EnforcementTransition(
            transition_id=f"transition-{uuid4()}",
            agent_id=agent.agent_id,
            action=action,
            actor=actor,
            reason=reason,
            previous_status=agent.status,
            new_status=new_status,
            trigger=trigger,
            occurred_at=now,
        )

        committed = self._enforcement_repository.record_transition(
            transition=transition,
            new_state=new_state,
            expected_epoch=expected_epoch,
        )
        if not committed:
            raise EnforcementConcurrencyError(
                f"Concurrent modification detected for agent '{agent.agent_id}' "
                f"(expected epoch {expected_epoch})"
            )

        # Fail-closed cross-repository persistence:
        # If save() raises, we do NOT roll back EnforcementStateRepository.
        # get_agent() projects SUSPENDED from EnforcementStateRepository, maintaining fail-closed security.
        updated = agent.model_copy(update={"status": new_status})
        self._agent_repository.save(updated)

        return updated
