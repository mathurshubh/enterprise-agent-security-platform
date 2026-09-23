"""SessionService — Sessions, ownership finality and lifecycle state (M4-S, M4-EVENT).

Security invariants:
- M4-S-1 (Terminal Ownership Finality): Once a session enters TERMINAL state, it cannot
  subsequently bind to any agent.
- M4-S-2 (Atomic Terminalization): Active session removal and tombstone creation occur
  atomically under one synchronization boundary.
- M4-S-3 (Ownership Preservation): An active session remains bound to its original agent.
- M4-S-4 (Fail-Closed Terminal Admission): Attempting to use a terminal session fails closed.
- M4-S-5 (Retention Separation): Terminal ownership tombstones are retained for process
  lifetime, separate from raw detection event retention.
- M4-S-6 (No Capacity Eviction of Security State): Tombstones cannot be discarded by capacity pressure.
- M4-EVENT-1 (Detection Horizon Preservation): Full detection evaluation horizon is preserved.
- M4-EVENT-2 (Effective Retention Horizon): Events are retained through the effective retention horizon.
- M4-EVENT-3 (Security-State Independence): Event pruning cannot mutate findings, risk posture,
  enforcement state, or tombstones.
- M4-EVENT-4 (Lifecycle-Bounded State): Retention is governed by detection horizon + grace, never arbitrary count.
- M4-EVENT-5 (Fail-Closed Compatibility Mode): retention_policy=None indicates explicit unbounded
  test/compatibility mode; pruning is disabled. Production bootstrap requires explicit policy.
- M4-EVENT-6 (Hot-Path Efficiency): Event insertion is O(log N); pruning is O(K log N) for K evicted
  events and does not require scanning retained events.
- M4-EVENT-7 (Timestamp Ordering Contract): Eviction correctness is guaranteed by min-heap root
  ordering and does not depend on insertion-order/timestamp monotonicity.
- M4-EVENT-8 (Canonical Deterministic Ordering): ``(timestamp, sequence_number)`` is
  the canonical deterministic ordering key for a session's history. Every recorded
  event carries a monotonic per-session ``sequence_number``, assigned once and never
  reassigned, serving as the immutable tie-breaker for equal timestamps. Chronological
  ordering (M4-EVENT-7) is unchanged; the tie-breaker makes a session's event order a
  property of the history rather than of internal heap layout, and pruning never
  renumbers survivors.
"""

import heapq
from datetime import datetime, timedelta, timezone
from threading import RLock

from app.models.detection_retention import DetectionRetentionPolicy
from app.models.session import (
    Session,
    TerminalReason,
    TerminalSessionTombstone,
)
from app.models.session_event import SessionEvent


class SessionAlreadyExistsError(Exception):
    pass


class SessionNotFoundError(Exception):
    pass


class SessionBindingError(Exception):
    """Raised when a session is used by an agent that does not own it.

    A session is security-owned by exactly one agent. Evidence gathered in a session
    feeds that agent's enforcement posture (M2b), so allowing another agent to write
    into it would let one workload manipulate another workload's security state.
    """

    def __init__(self, session_id: str, owner_agent_id: str, requested_agent_id: str) -> None:
        super().__init__(
            f"Session '{session_id}' is owned by agent '{owner_agent_id}', "
            f"not '{requested_agent_id}'"
        )
        self.session_id = session_id
        self.owner_agent_id = owner_agent_id
        self.requested_agent_id = requested_agent_id


class SessionTerminalError(SessionBindingError):
    """Raised when an operation attempts to use or rebind a terminal session (M4-S-1).

    Subclasses SessionBindingError so that existing security boundaries (such as
    RuntimeService and HTTP API handlers) catch it and fail closed with
    SESSION_BINDING_INVALID without leaking state or requiring broad refactoring.
    """

    def __init__(self, session_id: str, owner_agent_id: str, requested_agent_id: str) -> None:
        super().__init__(
            session_id=session_id,
            owner_agent_id=owner_agent_id,
            requested_agent_id=requested_agent_id,
        )


class SessionService:
    """Sessions and their ownership.

    Ownership is established once, atomically, and never changes. It is the integrity
    boundary for agent-scoped enforcement: behavioural evidence is only trustworthy if
    the agent it is attributed to is the agent that produced it.
    """

    def __init__(
        self,
        retention_policy: DetectionRetentionPolicy | None = None,
    ) -> None:
        """Initialize SessionService.

        Args:
            retention_policy: Authoritative detection retention policy (M4-EVENT).
                If None, operates in explicit unbounded test/compatibility mode
                where event pruning is disabled (M4-EVENT-5). Production bootstrapping
                must pass an explicit policy derived from DetectionService.
        """
        self._sessions: dict[str, Session] = {}
        self._tombstones: dict[str, TerminalSessionTombstone] = {}
        self._retention_policy = retention_policy
        self._events_heap: list[tuple[datetime, int, SessionEvent]] = []
        self._event_counter: int = 0
        # Canonical per-session position (M4-EVENT-8). Kept separately from the
        # heap so that pruning never renumbers surviving events and a sequence is
        # never reused after the events carrying it have been evicted.
        self._session_sequences: dict[str, int] = {}
        self._lock = RLock()

    @property
    def retention_policy(self) -> DetectionRetentionPolicy | None:
        return self._retention_policy

    def create_session(
        self,
        session: Session,
    ) -> Session:
        with self._lock:
            if session.session_id in self._tombstones:
                raise SessionTerminalError(
                    session.session_id,
                    self._tombstones[session.session_id].agent_id,
                    session.agent_id,
                )

            if session.session_id in self._sessions:
                raise SessionAlreadyExistsError()

            self._sessions[session.session_id] = session

            return session

    def get_session(
        self,
        session_id: str,
    ) -> Session:
        with self._lock:
            try:
                return self._sessions[session_id]
            except KeyError as exc:
                raise SessionNotFoundError() from exc

    def list_sessions(
        self,
    ) -> list[Session]:
        with self._lock:
            return list(self._sessions.values())

    def bind_or_validate(
        self,
        session_id: str,
        agent_id: str,
        now_utc: datetime | None = None,
    ) -> Session:
        """Return the session owned by ``agent_id``, establishing ownership if new.

        Establishment and validation happen under one lock, so two concurrent first
        uses cannot produce two competing owners: exactly one establishes ownership and
        the other is measured against it.

        Enforces M4-S-1 (Terminal Ownership Finality): a session ID in _tombstones
        fails closed permanently and cannot be rebound by any agent.

        Raises:
            SessionTerminalError: the session has reached terminal state.
            SessionBindingError: the session belongs to a different agent.
        """
        with self._lock:
            tombstone = self._tombstones.get(session_id)
            if tombstone is not None:
                raise SessionTerminalError(session_id, tombstone.agent_id, agent_id)

            existing = self._sessions.get(session_id)

            if existing is None:
                now = now_utc or datetime.now(timezone.utc)
                session = Session(
                    session_id=session_id,
                    agent_id=agent_id,
                    started_at=now,
                    last_activity_at=now,
                )
                self._sessions[session_id] = session
                return session

            if existing.agent_id != agent_id:
                raise SessionBindingError(session_id, existing.agent_id, agent_id)

            existing.last_activity_at = now_utc or datetime.now(timezone.utc)
            return existing

    def end_session(
        self,
        session_id: str,
        agent_id: str,
        *,
        now_utc: datetime | None = None,
    ) -> None:
        """Explicitly end an active session and atomically record a permanent tombstone (M4-S-2).

        Idempotent if called repeatedly by the owning agent.
        Raises:
            SessionNotFoundError: if session is unknown.
            SessionBindingError: if called by an agent that does not own the session.
        """
        with self._lock:
            tombstone = self._tombstones.get(session_id)
            if tombstone is not None:
                if tombstone.agent_id != agent_id:
                    raise SessionBindingError(session_id, tombstone.agent_id, agent_id)
                return

            existing = self._sessions.get(session_id)
            if existing is None:
                raise SessionNotFoundError(f"Session '{session_id}' not found")

            if existing.agent_id != agent_id:
                raise SessionBindingError(session_id, existing.agent_id, agent_id)

            now = now_utc or datetime.now(timezone.utc)
            del self._sessions[session_id]
            self._tombstones[session_id] = TerminalSessionTombstone(
                session_id=session_id,
                agent_id=agent_id,
                terminated_at=now,
                terminal_reason=TerminalReason.EXPLICIT_END,
            )

    def expire_idle_sessions(
        self,
        idle_threshold_seconds: float,
        now_utc: datetime | None = None,
    ) -> list[str]:
        """Authoritative idle expiration: transition idle active sessions to TERMINAL.

        Enforces M4-S-2: Active-session removal and tombstone creation occur atomically.
        """
        if idle_threshold_seconds <= 0:
            raise ValueError("idle_threshold_seconds must be positive")

        with self._lock:
            now = now_utc or datetime.now(timezone.utc)
            expired_ids: list[str] = []

            for session_id, session in list(self._sessions.items()):
                elapsed = (now - session.last_activity_at).total_seconds()
                if elapsed >= idle_threshold_seconds:
                    del self._sessions[session_id]
                    self._tombstones[session_id] = TerminalSessionTombstone(
                        session_id=session_id,
                        agent_id=session.agent_id,
                        terminated_at=now,
                        terminal_reason=TerminalReason.IDLE_TIMEOUT,
                    )
                    expired_ids.append(session_id)

            return expired_ids

    def is_terminal(self, session_id: str) -> bool:
        """Check if a session identifier is in terminal state."""
        with self._lock:
            return session_id in self._tombstones

    def get_tombstone(self, session_id: str) -> TerminalSessionTombstone | None:
        """Retrieve the terminal tombstone for a session if it exists."""
        with self._lock:
            return self._tombstones.get(session_id)

    def record_event(
        self,
        event: SessionEvent,
    ) -> SessionEvent:
        """Record a session event, refusing one attributed against session ownership.

        M4-EVENT-6: Hot-path insertion is O(log N).
        M4-EVENT-7: Stores into min-heap with sequence tie-breaker.
        """
        with self._lock:
            tombstone = self._tombstones.get(event.session_id)
            if tombstone is not None:
                raise SessionTerminalError(event.session_id, tombstone.agent_id, event.agent_id)

            owner = self._sessions.get(event.session_id)
            if owner is not None and owner.agent_id != event.agent_id:
                raise SessionBindingError(
                    event.session_id, owner.agent_id, event.agent_id
                )

            next_sequence = self._session_sequences.get(event.session_id, 0) + 1
            self._session_sequences[event.session_id] = next_sequence
            recorded = event.model_copy(update={"sequence_number": next_sequence})

            heapq.heappush(
                self._events_heap,
                (recorded.timestamp, self._event_counter, recorded),
            )
            self._event_counter += 1

            self._prune_events(now=recorded.timestamp)

            return recorded

    def _prune_events(self, now: datetime) -> int:
        """Prune expired session events whose timestamp is older than the retention cutoff.

        M4-EVENT-6: Pruning is O(K log N) for K evicted events and does not require scanning
        retained events.
        M4-EVENT-7: Root is guaranteed minimum timestamp; out-of-order events bubble up correctly.
        """
        if self._retention_policy is None:
            return 0

        cutoff = now - timedelta(seconds=self._retention_policy.total_retention_seconds)
        evicted = 0

        while self._events_heap and self._events_heap[0][0] < cutoff:
            heapq.heappop(self._events_heap)
            evicted += 1

        return evicted

    def prune_events(self, now_utc: datetime | None = None) -> int:
        """Explicit maintenance trigger to prune expired events under the lock."""
        with self._lock:
            now = now_utc or datetime.now(timezone.utc)
            return self._prune_events(now)

    def list_events(
        self,
        session_id: str,
    ) -> list[SessionEvent]:
        """Return the session's events in canonical order.

        M4-EVENT-6 / M4-EVENT-7: chronological, without assuming the heap array is
        itself sorted.

        M4-EVENT-8: the ordering key is ``(timestamp, sequence_number)``. Chronology
        remains primary; the persisted per-session sequence is the tie-breaker.
        Sorting on timestamp alone left tied events in whatever order the heap array
        happened to hold them, which is not insertion order and not stable across
        differently shaped histories, so anything deriving identity or evidence from
        "the first N events" had no deterministic answer. The tie-break is the
        persisted sequence, never the heap position.
        """
        with self._lock:
            matching = [
                item[2]
                for item in self._events_heap
                if item[2].session_id == session_id
            ]
            return sorted(matching, key=lambda e: (e.timestamp, e.sequence_number))