"""InMemoryEnforcementStateRepository — In-memory adapter for dynamic agent enforcement state (ADR-024, ADR-026, ADR-030)."""

from datetime import datetime
from threading import RLock

from app.models.agent_enforcement import (
    AgentEnforcementState,
    EnforcementAction,
    EnforcementTransition,
)
from app.repositories.interfaces.enforcement_state_repository import (
    EnforcementStateRepository,
)


class InMemoryEnforcementStateRepository(EnforcementStateRepository):
    """Thread-safe in-memory repository for agent enforcement state and epoch history.

    Invariants:
    - Object Isolation: Stored and returned entities are defensive deep copies.
    - Mandatory CAS Concurrency: record_transition requires expected_epoch matching persisted epoch.
      On match, atomically updates state, appends transition, and advances epoch to expected_epoch + 1.
      On mismatch, commits no changes and returns False.
    - Deterministic Ordering: list_transitions sorts by (occurred_at, transition_id).
    - Epoch Derivation: get_epoch derives count of REINSTATE transitions up to as_of.
    - Thread-Safe: Synchronized via threading.RLock.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._states: dict[str, AgentEnforcementState] = {}
        self._transitions: list[EnforcementTransition] = []
        self._epochs: dict[str, int] = {}

    def get_state(self, agent_id: str) -> AgentEnforcementState | None:
        with self._lock:
            state = self._states.get(agent_id)
            if state is None:
                return None
            return state.model_copy(deep=True)

    def record_transition(
        self,
        transition: EnforcementTransition,
        new_state: AgentEnforcementState,
        *,
        expected_epoch: int,
    ) -> bool:
        with self._lock:
            agent_id = transition.agent_id
            persisted_state = self._states.get(agent_id)
            current_epoch = (
                persisted_state.epoch
                if persisted_state is not None
                else self._epochs.get(agent_id, 0)
            )
            # Concurrency & validity invariants:
            # 1. Expected epoch must match current persisted epoch
            # 2. new_state.epoch must advance by exactly +1
            if current_epoch != expected_epoch or new_state.epoch != expected_epoch + 1:
                return False

            self._states[agent_id] = new_state.model_copy(deep=True)
            self._transitions.append(transition.model_copy(deep=True))
            self._epochs[agent_id] = expected_epoch + 1
            return True

    def list_transitions(
        self,
        agent_id: str | None = None,
    ) -> list[EnforcementTransition]:
        with self._lock:
            matching = [
                t
                for t in self._transitions
                if agent_id is None or t.agent_id == agent_id
            ]
            # Deterministic ordering: primary key occurred_at, secondary key transition_id
            ordered = sorted(matching, key=lambda t: (t.occurred_at, t.transition_id))
            return [t.model_copy(deep=True) for t in ordered]

    def get_epoch(
        self,
        agent_id: str,
        *,
        as_of: datetime,
    ) -> int:
        with self._lock:
            return sum(
                1
                for t in self._transitions
                if t.agent_id == agent_id
                and t.action == EnforcementAction.REINSTATE
                and t.occurred_at <= as_of
            )
