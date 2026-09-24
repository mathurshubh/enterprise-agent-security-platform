"""SessionRepository — Domain persistence protocol unifying session lifecycle, tombstones, and detection horizon (ADR-027, ADR-030)."""

from datetime import datetime
from typing import Protocol

from app.models.audit_event import Decision
from app.models.session import (
    Session,
    TerminalSessionTombstone,
)
from app.models.session_event import SessionEvent


class SessionRepository(Protocol):
    """Repository protocol unifying session lifecycle, terminal tombstones, and detection horizon (ADR-027, ADR-030).

    Invariants:
    - No Arbitrary Deletion: Active sessions cannot be deleted out-of-band; they must
      transition via terminalize_session() to preserve ownership finality (M4-S-1).
    - Atomic Terminalization: Active session removal and tombstone persistence occur
      atomically under a single synchronization boundary (M4-S-2).
    - Permanent Tombstones: Tombstones are retained permanently and never evicted under capacity pressure (M4-S-6).
    - Atomic Establishment: bind_or_create_session() atomically creates or touches an active session,
      failing closed on tombstone or ownership mismatch.
    - Repository Sequence Allocation: record_event() atomically allocates the next strictly increasing
      per-session sequence number (M4-EVENT-8). Callers cannot supply non-zero sequence numbers.
    - Sequence Continuity: Implementations of SessionRepository must preserve sequence continuity across
      their persistence lifecycle. The in-memory adapter guarantees continuity for its own lifetime;
      durable adapters must additionally guarantee restart recovery.
    - Session Event Existence Bound: record_event() strictly requires an existing, active session owned
      by the calling agent; orphaned events are rejected.
    - Single-Transition Final Decision Finalization: update_event_final_decision() may modify only the
      previously-unset (None) final_decision field of the uniquely identified event. Historical fields
      (timestamp, agent_id, session_id, decision, sequence_number) remain immutable security evidence.
      Transitions from an already-finalized value are rejected.
    - Rolling Horizon: Detection events maintain sliding window retention with canonical deterministic ordering.
      Pruning never resets the per-session sequence counter or renumbers survivors.
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

    def save_tombstone(self, tombstone: TerminalSessionTombstone) -> None:
        """Persist a terminal session tombstone directly."""
        ...

    def terminalize_session(
        self,
        session_id: str,
        tombstone: TerminalSessionTombstone,
    ) -> bool:
        """Atomically remove an active session and persist its terminal tombstone.

        Returns True if the session was active and terminalized, or False if the session
        was not found or was already terminal.
        """
        ...

    def record_event(self, event: SessionEvent) -> SessionEvent:
        """Atomically allocate the next strictly increasing per-session sequence and persist the event.

        Raises:
            SessionTerminalError: if session reached terminal state.
            SessionNotFoundError: if active session does not exist.
            SessionBindingError: if active session belongs to a different agent.
            ValueError: if event carries a non-zero caller-supplied sequence_number.
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

        May modify only the previously-unset (final_decision is None) field of the uniquely
        identified event. Preserves all other historical fields (timestamp, agent_id, session_id,
        decision, sequence_number) as immutable security evidence.

        Raises:
            SessionTerminalError: if session reached terminal state.
            SessionNotFoundError: if active session does not exist.
            ValueError: if no matching event with sequence_number exists in the session,
                or if the event's final_decision has already been finalized to a different value.
        """
        ...
