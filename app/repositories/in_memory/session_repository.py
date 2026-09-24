"""InMemorySessionRepository — In-memory adapter for session lifecycle, tombstones, and detection horizon (ADR-027, ADR-030)."""

from datetime import datetime
from threading import RLock

from app.models.session import Session, TerminalSessionTombstone
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
    - No Arbitrary Deletion: No delete_session method exists.
    - Deterministic Ordering: list_events sorts by (timestamp, sequence_number).
    - Thread-Safe: Synchronized via threading.RLock.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, Session] = {}
        self._tombstones: dict[str, TerminalSessionTombstone] = {}
        self._events: list[SessionEvent] = []

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

    def record_event(self, event: SessionEvent) -> None:
        with self._lock:
            self._events.append(event.model_copy(deep=True))

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
            return initial - len(self._events)
