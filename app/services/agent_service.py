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
from app.repositories.interfaces.agent_repository import AgentRepository
from app.repositories.interfaces.enforcement_state_repository import (
    EnforcementStateRepository,
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


class EnforcementConcurrencyError(Exception):
    """Raised when an enforcement state transition fails due to concurrent modification (CAS epoch mismatch)."""


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
    ) -> None:
        self._lock = RLock()
        self._agent_repository = agent_repository
        self._enforcement_repository = enforcement_repository

    @property
    def agent_repository(self) -> AgentRepository:
        """Injected AgentRepository protocol instance."""
        return self._agent_repository

    @property
    def enforcement_repository(self) -> EnforcementStateRepository:
        """Injected EnforcementStateRepository protocol instance."""
        return self._enforcement_repository

    def register_agent(self, agent: Agent) -> Agent:
        with self._lock:
            existing = self._agent_repository.get(agent.agent_id)
            if existing is not None:
                raise AgentAlreadyExistsError(
                    f"Agent '{agent.agent_id}' already exists"
                )

            self._agent_repository.save(agent)
            return agent

    def get_agent(self, agent_id: str) -> Agent:
        with self._lock:
            agent = self._agent_repository.get(agent_id)
            if agent is None:
                raise AgentNotFoundError(f"Agent '{agent_id}' not found")

            # Dynamic enforcement posture projection (fail-closed)
            if agent.status != AgentStatus.DISABLED:
                enf_state = self._enforcement_repository.get_state(agent_id)
                if enf_state is not None and enf_state.suspended_at is not None:
                    agent = agent.model_copy(update={"status": AgentStatus.SUSPENDED})

            return agent

    def list_agents(self) -> list[Agent]:
        with self._lock:
            agents = self._agent_repository.list()
            projected = []
            for agent in agents:
                if agent.status != AgentStatus.DISABLED:
                    enf_state = self._enforcement_repository.get_state(agent.agent_id)
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

        # get_epoch() returns the reinstatement/recovery epoch (R); the CAS expected
        # transition epoch is derived as 2 * recovery_epoch for SUSPEND and
        # 2 * recovery_epoch + 1 for REINSTATE.
        recovery_epoch = self._enforcement_repository.get_epoch(
            agent.agent_id, as_of=now
        )
        if action == EnforcementAction.SUSPEND:
            expected_epoch = 2 * recovery_epoch
        else:
            expected_epoch = 2 * recovery_epoch + 1

        state = self._enforcement_repository.get_state(agent.agent_id)
        if state is None:
            state = AgentEnforcementState(agent_id=agent.agent_id)

        if action == EnforcementAction.SUSPEND:
            new_state = state.model_copy(
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
            new_state = state.model_copy(
                update={
                    "suspended_at": None,
                    "suspension_reason": None,
                    "enforcement_baseline_at": baseline_at,
                    "enforcement_baseline_sequence": baseline_seq,
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
