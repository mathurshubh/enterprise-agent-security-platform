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
    ) -> Agent:
        """Return a suspended agent to service under a new enforcement baseline.

        This is the only transition out of ``SUSPENDED``. It preserves every finding
        and every recorded transition: the baseline changes which evidence still drives
        enforcement, not what the platform observed.

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

    def _transition(
        self,
        agent: Agent,
        new_status: AgentStatus,
        action: EnforcementAction,
        actor: str,
        reason: str,
        trigger: EnforcementTrigger | None,
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
            state = state.model_copy(
                update={
                    "suspended_at": None,
                    "suspension_reason": None,
                    "enforcement_baseline_at": now,
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
