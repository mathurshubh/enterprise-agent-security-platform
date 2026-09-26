from datetime import datetime, timedelta
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
from app.models.session_event import (
    AggregationScope,
    HorizonQuery,
    SessionEvent,
)
from app.repositories.interfaces.session_repository import SessionRepository


class InMemorySessionRepository(SessionRepository):
    """Thread-safe in-memory repository unifying session lifecycle, tombstones, and detection horizon.

    Invariants:
    - Object Isolation: Stored and returned entities are defensive deep copies.
    - Atomic Terminalization: terminalize_session atomically transitions the session to terminal
      and records a terminal tombstone under one lock.
    - Atomic Establishment: bind_or_create_session atomically creates or touches an active session,
      failing closed on tombstone or ownership mismatch.
    - Strictly Increasing Dual Sequence Allocation: record_event atomically allocates both the next
      per-session sequence_number and the next per-agent agent_sequence. Callers cannot supply non-zero values.
    - Monotonic Ordering: agent_sequence is strictly monotonic per agent; numerical gaplessness is not required.
    - Atomic Last Activity Touch: record_event touches active session's last_activity_at = event.timestamp.
    - Horizon Eligibility: list_eligible_events filters by scope (SESSION vs AGENT), temporal window,
      and monotonic baseline sequence watermark (agent_sequence > query.baseline_agent_sequence).
    - Deterministic Ordering:
        scope == AGENT queries order by agent_sequence ASC.
        scope == SESSION queries order by sequence_number ASC.
    - Sequence Retention Independence: Event pruning never renumbers surviving events or resets sequence counters.
    - Thread-Safe: Synchronized via threading.RLock.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, Session] = {}
        self._tombstones: dict[str, TerminalSessionTombstone] = {}
        self._events: list[SessionEvent] = []
        self._session_sequences: dict[str, int] = {}
        self._agent_sequences: dict[str, int] = {}

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

            if event.agent_sequence != 0:
                raise ValueError(
                    f"Cannot record event with caller-supplied agent_sequence={event.agent_sequence}; "
                    f"sequence allocation is strictly repository-owned."
                )

            next_seq = self._session_sequences.get(event.session_id, 0) + 1
            self._session_sequences[event.session_id] = next_seq

            next_agent_seq = self._agent_sequences.get(event.agent_id, 0) + 1
            self._agent_sequences[event.agent_id] = next_agent_seq

            active.last_activity_at = event.timestamp

            persisted = event.model_copy(
                update={
                    "sequence_number": next_seq,
                    "agent_sequence": next_agent_seq,
                },
                deep=True,
            )
            self._events.append(persisted.model_copy(deep=True))
            return persisted.model_copy(deep=True)

    def list_eligible_events(self, query: HorizonQuery) -> list[SessionEvent]:
        with self._lock:
            cutoff = query.evaluation_time - timedelta(seconds=query.window_seconds)

            matching: list[SessionEvent] = []
            for ev in self._events:
                if ev.agent_id != query.agent_id:
                    continue
                if (
                    query.scope == AggregationScope.SESSION
                    and ev.session_id != query.session_id
                ):
                    continue
                if ev.agent_sequence <= query.baseline_agent_sequence:
                    continue
                if ev.timestamp < cutoff or ev.timestamp > query.evaluation_time:
                    continue
                matching.append(ev)

            # Deterministic primary ordering:
            # - scope == AGENT: ORDER BY agent_sequence ASC
            # - scope == SESSION: ORDER BY sequence_number ASC
            if query.scope == AggregationScope.AGENT:
                ordered = sorted(matching, key=lambda e: e.agent_sequence)
            else:
                ordered = sorted(matching, key=lambda e: e.sequence_number)

            return [e.model_copy(deep=True) for e in ordered]

    def list_events(self, session_id: str) -> list[SessionEvent]:
        with self._lock:
            matching = [e for e in self._events if e.session_id == session_id]
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
