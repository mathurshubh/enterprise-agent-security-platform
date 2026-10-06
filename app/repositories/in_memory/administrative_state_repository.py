"""InMemoryAdministrativeStateRepository — in-memory adapter for administrative lifecycle state.

ADR-024 A.6/A.8, ADR-030 L.3, AP.4. Process-local locking reduces contention here; it is
never the correctness mechanism the contract relies on (ADR-024 A.6), and the SQL adapter
must reproduce these semantics with durable row locking rather than inherit them.
"""

from threading import RLock

from app.models.agent_administrative import (
    AdministrativeTransition,
    AgentAdministrativeState,
    is_legal_administrative_transition,
)
from app.repositories.interfaces.administrative_state_repository import (
    AdministrativeStateRepository,
    AdministrativeTransitionInvariantError,
)


class InMemoryAdministrativeStateRepository(AdministrativeStateRepository):
    """Thread-safe in-memory administrative state and ledger.

    Invariants (mirroring the protocol):
    - Object Isolation: stored and returned entities are defensive deep copies.
    - Mandatory CAS: record_transition requires expected_version.
    - Outcome Separation: a lost update returns False; an invariant violation raises.
    - Atomicity: on any refusal neither the state nor the ledger is touched.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._states: dict[str, AgentAdministrativeState] = {}
        self._transitions: list[AdministrativeTransition] = []

    def get_state(self, agent_id: str) -> AgentAdministrativeState | None:
        with self._lock:
            state = self._states.get(agent_id)
            return None if state is None else state.model_copy(deep=True)

    def record_transition(
        self,
        transition: AdministrativeTransition,
        new_state: AgentAdministrativeState,
        *,
        expected_version: int,
    ) -> bool:
        with self._lock:
            agent_id = transition.agent_id
            persisted = self._states.get(agent_id)
            current_version = persisted.administrative_version if persisted else 0

            # Compare-and-set first. A version mismatch is a lost update: another
            # transition committed since the caller read, and re-reading repairs it.
            if current_version != expected_version:
                return False

            # Everything below is an invariant, not a race. Checked after the CAS so a
            # concurrent writer cannot make a stale caller look like a malformed one.
            if new_state.administrative_version != expected_version + 1:
                raise AdministrativeTransitionInvariantError(
                    f"Administrative version must advance by exactly one for agent "
                    f"'{agent_id}': expected {expected_version + 1}, offered "
                    f"{new_state.administrative_version}."
                )

            previous_state = persisted.state if persisted else None
            if not is_legal_administrative_transition(previous_state, new_state.state):
                raise AdministrativeTransitionInvariantError(
                    f"Illegal administrative transition for agent '{agent_id}': "
                    f"{previous_state.value if previous_state else 'none'} -> "
                    f"{new_state.state.value}."
                )

            # The ledger must describe the transition that actually happened, so its
            # endpoints are validated against the persisted state rather than trusted.
            if (
                transition.previous_state != previous_state
                or transition.new_state != new_state.state
                or transition.administrative_version_before != current_version
                or transition.administrative_version_after
                != new_state.administrative_version
            ):
                raise AdministrativeTransitionInvariantError(
                    f"Ledger entry does not describe the transition being committed for "
                    f"agent '{agent_id}'. A ledger that disagrees with the state it "
                    f"records is not evidence of it."
                )

            self._states[agent_id] = new_state.model_copy(deep=True)
            self._transitions.append(transition.model_copy(deep=True))
            return True

    def list_transitions(
        self,
        agent_id: str | None = None,
    ) -> list[AdministrativeTransition]:
        with self._lock:
            matching = [
                t
                for t in self._transitions
                if agent_id is None or t.agent_id == agent_id
            ]
            ordered = sorted(matching, key=lambda t: (t.occurred_at, t.transition_id))
            return [t.model_copy(deep=True) for t in ordered]
