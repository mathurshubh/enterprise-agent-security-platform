"""InMemorySessionRepository — In-memory adapter for session lifecycle, tombstones, and detection horizon (ADR-027, ADR-030)."""

from datetime import datetime
from threading import RLock

from app.models.audit_event import Decision
from app.models.session import (
    Session,
    SessionAlreadyExistsError,
    SessionBindingError,
    SessionNotFoundError,
    SessionTerminalError,
    TerminalSessionTombstone,
)
from app.models.session_event import SessionEvent
from app.repositories.interfaces.session_repository import SessionRepository


class InMemorySessionRepository(SessionRepository):
    """Thread-safe in-memory repository unifying session lifecycle, tombstones, and detection horizon.

    Invariants:
    - Object Isolation: Stored and returned entities are defensive deep copies.
    - Atomic Terminalization: terminalize_session atomically removes the active session
      and records a terminal tombstone under one lock.
      A successful terminalization never leaves the session simultaneously in both _sessions and _tombstones.
      A failed terminalization modifies neither collection.
    - Atomic Establishment: bind_or_create_session atomically creates or touches an active session,
      failing closed on tombstone or ownership mismatch.
    - Strictly Increasing Sequence Allocation: record_event atomically allocates the next
      per-session sequence number (1 < 2 < 3 ...). Callers cannot supply non-zero sequence numbers.
    - Sequence Continuity: Implementations of SessionRepository must preserve sequence continuity across
      their persistence lifecycle. The in-memory adapter guarantees continuity for its own lifetime;
      durable adapters must additionally guarantee restart recovery.
    - Session Event Existence Bound: record_event requires an active session owned by the caller;
      orphaned events for nonexistent sessions are rejected.
    - Single-Transition Final Decision Finalization: update_event_final_decision() may modify only the
      previously-unset (None) final_decision field of the uniquely identified event. Historical fields
      (timestamp, agent_id, session_id, decision, sequence_number) remain immutable security evidence.
      Transitions from an already-finalized value are rejected.
    - No Arbitrary Deletion: No delete_session method exists.
    - Deterministic Ordering: list_events sorts by (timestamp, sequence_number).
    - Sequence Retention Independence: Event pruning never renumbers surviving events or resets sequence counters.
    - Thread-Safe: Synchronized via threading.RLock.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, Session] = {}
        self._tombstones: dict[str, TerminalSessionTombstone] = {}
        self._events: list[SessionEvent] = []
        self._session_sequences: dict[str, int] = {}

    def get_session(self, session_id: str) -> Session | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            return session.model_copy(deep=True)

    def save_session(self, session: Session) -> None:
        with self._lock:
            self._sessions[session.session_id] = session.model_copy(deep=True)

    def list_sessions(self) -> list[Session]:
        with self._lock:
            return [s.model_copy(deep=True) for s in self._sessions.values()]

    def create_session(self, session: Session) -> Session:
        with self._lock:
            if session.session_id in self._tombstones:
                raise SessionTerminalError(
                    session.session_id,
                    self._tombstones[session.session_id].agent_id,
                    session.agent_id,
                )
            if session.session_id in self._sessions:
                raise SessionAlreadyExistsError(
                    f"Session '{session.session_id}' already exists"
                )
            self._sessions[session.session_id] = session.model_copy(deep=True)
            return session.model_copy(deep=True)

    def bind_or_create_session(
        self,
        session_id: str,
        agent_id: str,
        *,
        now: datetime,
    ) -> Session:
        with self._lock:
            if session_id in self._tombstones:
                raise SessionTerminalError(
                    session_id,
                    self._tombstones[session_id].agent_id,
                    agent_id,
                )

            existing = self._sessions.get(session_id)
            if existing is None:
                session = Session(
                    session_id=session_id,
                    agent_id=agent_id,
                    started_at=now,
                    last_activity_at=now,
                )
                self._sessions[session_id] = session.model_copy(deep=True)
                return session.model_copy(deep=True)

            if existing.agent_id != agent_id:
                raise SessionBindingError(session_id, existing.agent_id, agent_id)

            existing.last_activity_at = now
            return existing.model_copy(deep=True)

    def get_tombstone(self, session_id: str) -> TerminalSessionTombstone | None:
        with self._lock:
            tombstone = self._tombstones.get(session_id)
            if tombstone is None:
                return None
            return tombstone.model_copy(deep=True)

    def save_tombstone(self, tombstone: TerminalSessionTombstone) -> None:
        with self._lock:
            self._tombstones[tombstone.session_id] = tombstone.model_copy(deep=True)

    def terminalize_session(
        self,
        session_id: str,
        tombstone: TerminalSessionTombstone,
    ) -> bool:
        with self._lock:
            # Must be active and not already terminal
            if session_id not in self._sessions:
                return False
            if session_id in self._tombstones:
                return False

            del self._sessions[session_id]
            self._tombstones[session_id] = tombstone.model_copy(deep=True)
            return True

    def record_event(self, event: SessionEvent) -> SessionEvent:
        with self._lock:
            if event.session_id in self._tombstones:
                raise SessionTerminalError(
                    event.session_id,
                    self._tombstones[event.session_id].agent_id,
                    event.agent_id,
                )

            active = self._sessions.get(event.session_id)
            if active is None:
                raise SessionNotFoundError(
                    f"Session '{event.session_id}' not found; cannot record event for nonexistent session"
                )

            if active.agent_id != event.agent_id:
                raise SessionBindingError(
                    event.session_id,
                    active.agent_id,
                    event.agent_id,
                )

            if event.sequence_number != 0:
                raise ValueError(
                    f"Cannot record event with caller-supplied sequence_number={event.sequence_number}; "
                    f"sequence allocation is strictly repository-owned."
                )

            next_seq = self._session_sequences.get(event.session_id, 0) + 1
            self._session_sequences[event.session_id] = next_seq

            persisted = event.model_copy(
                update={"sequence_number": next_seq},
                deep=True,
            )
            self._events.append(persisted.model_copy(deep=True))
            return persisted.model_copy(deep=True)

    def list_events(self, session_id: str) -> list[SessionEvent]:
        with self._lock:
            matching = [e for e in self._events if e.session_id == session_id]
            # Deterministic ordering: primary key timestamp, secondary key sequence_number
            ordered = sorted(
                matching,
                key=lambda e: (
                    e.timestamp,
                    e.sequence_number if e.sequence_number is not None else 0,
                ),
            )
            return [e.model_copy(deep=True) for e in ordered]

    def prune_events(self, *, cutoff: datetime) -> int:
        with self._lock:
            initial = len(self._events)
            self._events = [e for e in self._events if e.timestamp >= cutoff]
            # Invariant: self._session_sequences is untouched by pruning
            return initial - len(self._events)

    def update_event_final_decision(
        self,
        session_id: str,
        sequence_number: int,
        final_decision: Decision,
    ) -> None:
        """Atomically finalize the final_decision on an existing recorded session event."""
        with self._lock:
            if session_id in self._tombstones:
                tomb = self._tombstones[session_id]
                raise SessionTerminalError(session_id, tomb.agent_id, tomb.agent_id)
            if session_id not in self._sessions:
                raise SessionNotFoundError(f"Session '{session_id}' not found")
            for ev in self._events:
                if (
                    ev.session_id == session_id
                    and ev.sequence_number == sequence_number
                ):
                    if (
                        ev.final_decision is not None
                        and ev.final_decision != final_decision
                    ):
                        raise ValueError(
                            f"Event {sequence_number} in session '{session_id}' is already finalized "
                            f"as {ev.final_decision} and cannot transition to {final_decision}"
                        )
                    ev.final_decision = final_decision
                    return
            raise ValueError(
                f"Event with sequence {sequence_number} not found for session '{session_id}'"
            )
