"""SessionRepository — Domain persistence protocols for session lifecycle and detection horizon (ADR-027, ADR-030)."""

from datetime import datetime
from typing import Protocol

from app.models.audit_event import Decision
from app.models.session import (
    Session,
    TerminalSessionTombstone,
)
from app.models.session_event import (
    AggregationScope,
    HorizonQuery,
    SessionEvent,
)

__all__ = [
    "AggregationScope",
    "HorizonQuery",
    "SessionEventHorizonRepository",
    "SessionLifecycleRepository",
    "SessionRepository",
]


class SessionLifecycleRepository(Protocol):
    """Repository protocol governing session identity, ownership, and terminal lifecycle (M4-S).

    Invariants:
    - Ownership Finality: Once established, an active session cannot bind to another agent (M4-S-1).
    - Atomic Terminalization: Active session state transition and tombstone creation occur
      atomically under a single synchronization boundary (M4-S-2).
    - Preserved Identity: Terminalization transitions lifecycle state to TERMINAL; it does not
      physically destroy the session identity, preserving foreign-key referential integrity.
    - Permanent Tombstones: Tombstones are retained permanently and never evicted under capacity pressure (M4-S-6).
    - Atomic Establishment: bind_or_create_session() atomically creates or touches an active session,
      failing closed on tombstone or ownership mismatch.
    - No Arbitrary Deletion: Active sessions cannot be deleted out-of-band.
    """

    def get_session(self, session_id: str) -> Session | None:
        """Retrieve an active session by session_id, or None if not found."""
        ...

    def save_session(self, session: Session) -> None:
        """Persist or update an active session."""
        ...

    def list_sessions(self) -> list[Session]:
        """List all active sessions."""
        ...

    def create_session(self, session: Session) -> Session:
        """Atomically create a new active session.

        Raises:
            SessionTerminalError: if a terminal tombstone exists for session_id.
            SessionAlreadyExistsError: if an active session already exists.
        """
        ...

    def bind_or_create_session(
        self,
        session_id: str,
        agent_id: str,
        *,
        now: datetime,
    ) -> Session:
        """Atomically establish ownership or validate an existing active session.

        Raises:
            SessionTerminalError: if session reached terminal state.
            SessionBindingError: if active session belongs to a different agent.
        """
        ...

    def get_tombstone(self, session_id: str) -> TerminalSessionTombstone | None:
        """Retrieve a terminal session tombstone if it exists."""
        ...

    def terminalize_session(
        self,
        session_id: str,
        tombstone: TerminalSessionTombstone,
    ) -> bool:
        """Atomically transition an active session to terminal and persist its tombstone.

        Returns True if the session was active and terminalized, or False if the session
        was not found or was already terminal.
        """
        ...


class SessionEventHorizonRepository(Protocol):
    """Repository protocol governing behavioral event sequencing, horizon queries, and pruning (M4-EVENT).

    Invariants:
    - Atomic Event Recording Boundary: record_event() executes as a single atomic transition:
        1. Resolves active session.
        2. Verifies agent ownership (session.agent_id == event.agent_id).
        3. Verifies non-terminal state (fails closed if tombstone exists).
        4. Validates event carries unassigned sequences (sequence_number == 0 and agent_sequence == 0).
        5. Atomically allocates next monotonic session sequence_number.
        6. Atomically allocates next monotonic agent_sequence (strictly increasing; gaplessness not required).
        7. Touches active session's last_activity_at = event.timestamp.
        8. Persists the event.
      Failure at any step aborts the operation and mutates neither session nor event state.
    - Sequence Continuity: Pruning never resets sequence counters or renumbers surviving events.
    - Horizon Eligibility: list_eligible_events() applies scope (SESSION vs AGENT), monotonic baseline
      sequence watermark (event.agent_sequence > query.baseline_agent_sequence), and snapshot temporal
      bounds (query.evaluation_time - window <= event.timestamp <= query.evaluation_time).
      A detection invocation evaluates the horizon as of the triggering event's timestamp (evaluation_time),
      guaranteeing deterministic snapshot replay semantics. Future-dated events (> evaluation_time) are excluded.
    - Authoritative Ordering vs Temporal Eligibility: agent_sequence establishes authoritative behavioral
      ordering; timestamp establishes temporal-window eligibility.
    - Deterministic Ordering:
        scope == AGENT queries order by event.agent_sequence ASC.
        scope == SESSION queries order by event.sequence_number ASC.
    - Decision Finalization Immutability: update_event_final_decision() allows None -> Decision,
      and permits idempotent updates to the same decision, but strictly rejects mutations from an
      already-finalized decision to a different decision.
    """

    def record_event(self, event: SessionEvent) -> SessionEvent:
        """Atomically validate session state, allocate both sequence positions, and persist the event.

        Raises:
            SessionTerminalError: if session reached terminal state.
            SessionNotFoundError: if active session does not exist.
            SessionBindingError: if active session belongs to a different agent.
            ValueError: if event carries non-zero caller-supplied sequence numbers.
        """
        ...

    def list_eligible_events(self, query: HorizonQuery) -> list[SessionEvent]:
        """Return defensive copies of events eligible for behavioral detection under the query specification.

        Raises:
            SessionRepositoryError: if persistence is unavailable or queries fail.
        """
        ...

    def list_events(self, session_id: str) -> list[SessionEvent]:
        """Return recorded events for a session in canonical deterministic order."""
        ...

    def prune_events(self, *, cutoff: datetime) -> int:
        """Prune detection horizon events older than the cutoff timestamp. Returns count evicted."""
        ...

    def update_event_final_decision(
        self,
        session_id: str,
        sequence_number: int,
        final_decision: Decision,
    ) -> None:
        """Atomically finalize the final_decision on an existing recorded session event.

        Raises:
            SessionTerminalError: if session reached terminal state.
            SessionNotFoundError: if active session does not exist.
            ValueError: if no matching event with sequence_number exists in the session,
                or if the event's final_decision has already been finalized to a different value.
        """
        ...


class SessionRepository(SessionLifecycleRepository, SessionEventHorizonRepository, Protocol):
    """Unified repository protocol unifying session lifecycle and detection horizon (ADR-027, ADR-030)."""
