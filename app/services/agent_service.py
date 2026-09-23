from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from app.models.agent import Agent, AgentStatus
from app.models.agent_enforcement import (
    AgentEnforcementState,
    EnforcementAction,
    EnforcementTransition,
    EnforcementTrigger,
)
from app.models.watermark import BaselineWatermark

# Suspension is written by the deterministic runtime pipeline, never by an operator
# request. Reinstatement is the opposite: it always names the operator who performed it.
RUNTIME_ACTOR = "runtime"


class AgentAlreadyExistsError(Exception):
    """Raised when attempting to register an existing agent."""


class AgentNotFoundError(Exception):
    """Raised when an agent cannot be found."""


class AgentNotSuspendedError(Exception):
    """Raised when reinstating an agent that is not suspended."""


class AgentService:
    """Registry of agents and the authority for their enforcement state (M2b).

    Enforcement state is monotonic from the runtime's perspective: the pipeline may
    suspend an agent, and only an explicit, attributed reinstatement returns it to
    service. No other method on this service produces that transition.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._agents: dict[str, Agent] = {}
        self._enforcement: dict[str, AgentEnforcementState] = {}
        # Append-only governance history, kept outside AgentEnforcementState so the
        # current state remains a value object rather than a growing event log.
        self._transitions: list[EnforcementTransition] = []

    def register_agent(self, agent: Agent) -> Agent:
        with self._lock:
            if agent.agent_id in self._agents:
                raise AgentAlreadyExistsError(
                    f"Agent '{agent.agent_id}' already exists"
                )

            self._agents[agent.agent_id] = agent
            return agent

    def get_agent(self, agent_id: str) -> Agent:
        with self._lock:
            if agent_id not in self._agents:
                raise AgentNotFoundError(
                    f"Agent '{agent_id}' not found"
                )

            return self._agents[agent_id]

    def list_agents(self) -> list[Agent]:
        with self._lock:
            return list(self._agents.values())

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
                raise AgentNotSuspendedError(
                    f"Agent '{agent_id}' is not suspended"
                )

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

        Reads the stored enforcement_baseline_at and enforcement_baseline_sequence.
        Never derives or recomputes a new baseline from findings.
        """
        with self._lock:
            state = self.get_enforcement_state(agent_id)
            return BaselineWatermark(
                agent_id=agent_id,
                baseline_at=state.enforcement_baseline_at,
                baseline_sequence=state.enforcement_baseline_sequence,
            )

    def get_enforcement_state(self, agent_id: str) -> AgentEnforcementState:
        """Return the agent's current enforcement state."""
        with self._lock:
            self.get_agent(agent_id)
            return self._enforcement.get(
                agent_id,
                AgentEnforcementState(agent_id=agent_id),
            )

    def list_transitions(
        self,
        agent_id: str | None = None,
    ) -> list[EnforcementTransition]:
        """Return recorded enforcement transitions in chronological order."""
        with self._lock:
            if agent_id is None:
                return list(self._transitions)
            return [
                transition
                for transition in self._transitions
                if transition.agent_id == agent_id
            ]

    def enforcement_epoch(
        self,
        agent_id: str,
        *,
        as_of: datetime,
    ) -> int:
        """Return how many times this agent had been reinstated by ``as_of``.

        Derived from the append-only transition history rather than stored, and
        evaluated at a supplied moment rather than "now". Detection identity
        depends on it, so reading the agent's *current* epoch would make the
        identity of a past event depend on when it is looked at: an event from
        before a reinstatement would derive one epoch live and a different one on
        replay, and the same behaviour would produce two different findings.

        Neither ``baseline_sequence`` nor ``baseline_at`` can serve this purpose.
        Two reinstatements with no evidence between them share a baseline sequence,
        and a baseline timestamp is a wall-clock capture rather than a position in
        the history being replayed.
        """
        with self._lock:
            return sum(
                1
                for transition in self._transitions
                if transition.agent_id == agent_id
                and transition.action == EnforcementAction.REINSTATE
                and transition.occurred_at <= as_of
            )

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
        """Apply one enforcement transition atomically under the service lock."""
        now = datetime.now(timezone.utc)
        # Replace the stored record rather than mutating it, so a caller holding a
        # reference never observes a partially updated agent.
        updated = agent.model_copy(update={"status": new_status})
        self._agents[agent.agent_id] = updated

        state = self._enforcement.get(
            agent.agent_id,
            AgentEnforcementState(agent_id=agent.agent_id),
        )
        if action == EnforcementAction.SUSPEND:
            state = state.model_copy(
                update={
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
            baseline_seq = watermark.baseline_sequence if watermark else 0
            state = state.model_copy(
                update={
                    "suspended_at": None,
                    "suspension_reason": None,
                    "enforcement_baseline_at": baseline_at,
                    "enforcement_baseline_sequence": baseline_seq,
                    "last_transition_at": now,
                }
            )
        self._enforcement[agent.agent_id] = state

        self._transitions.append(
            EnforcementTransition(
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
        )

        return updated
