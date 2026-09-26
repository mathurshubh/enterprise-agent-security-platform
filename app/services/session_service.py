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

from datetime import datetime, timedelta, timezone

from app.models.audit_event import Decision
from app.models.detection_retention import DetectionRetentionPolicy
from app.models.session import (
    Session,
    SessionAlreadyExistsError,
    SessionBindingError,
    SessionNotFoundError,
    SessionTerminalError,
    TerminalReason,
    TerminalSessionTombstone,
)
from app.models.session_event import HorizonQuery, SessionEvent
from app.repositories.interfaces.session_repository import SessionRepository

__all__ = [
    "SessionAlreadyExistsError",
    "SessionBindingError",
    "SessionNotFoundError",
    "SessionService",
    "SessionTerminalError",
]


class SessionService:
    """Sessions and their ownership (M4-S, M4-EVENT, PR #183).

    Ownership is established once, atomically, and never changes. It is the integrity
    boundary for agent-scoped enforcement: behavioural evidence is only trustworthy if
    the agent it is attributed to is the agent that produced it.

    In PR #183, SessionRepository is the sole authoritative state source (no internal dicts,
    heaps, or local sequence counters).
    """

    def __init__(
        self,
        session_repository: SessionRepository,
        retention_policy: DetectionRetentionPolicy | None = None,
    ) -> None:
        """Initialize SessionService.

        Args:
            session_repository: Injected SessionRepository protocol instance (required in PR #183).
            retention_policy: Authoritative detection retention policy (M4-EVENT).
                If None, operates in explicit unbounded test/compatibility mode
                where event pruning is disabled (M4-EVENT-5). Production bootstrapping
                must pass an explicit policy derived from DetectionService.
        """
        self._session_repository = session_repository
        self._retention_policy = retention_policy

    @property
    def session_repository(self) -> SessionRepository:
        """Injected SessionRepository protocol instance."""
        return self._session_repository

    @property
    def retention_policy(self) -> DetectionRetentionPolicy | None:
        return self._retention_policy

    def create_session(
        self,
        session: Session,
    ) -> Session:
        """Create a new active session via authoritative repository."""
        return self._session_repository.create_session(session)

    def get_session(
        self,
        session_id: str,
    ) -> Session:
        """Retrieve an active session, raising SessionNotFoundError if missing."""
        session = self._session_repository.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session '{session_id}' not found")
        return session

    def list_sessions(
        self,
    ) -> list[Session]:
        """List all active sessions from authoritative repository."""
        return self._session_repository.list_sessions()

    def bind_or_validate(
        self,
        session_id: str,
        agent_id: str,
        now_utc: datetime | None = None,
    ) -> Session:
        """Return the session owned by ``agent_id``, establishing ownership if new.

        Delegates to repository's atomic bind_or_create_session primitive.
        """
        now = now_utc or datetime.now(timezone.utc)
        return self._session_repository.bind_or_create_session(
            session_id=session_id,
            agent_id=agent_id,
            now=now,
        )

    def end_session(
        self,
        session_id: str,
        agent_id: str,
        *,
        now_utc: datetime | None = None,
    ) -> None:
        """Explicitly end an active session and atomically record a permanent tombstone (M4-S-2).

        Idempotent if called repeatedly by the owning agent.
        """
        now = now_utc or datetime.now(timezone.utc)
        tombstone = self._session_repository.get_tombstone(session_id)
        if tombstone is not None:
            if tombstone.agent_id != agent_id:
                raise SessionBindingError(session_id, tombstone.agent_id, agent_id)
            return

        existing = self._session_repository.get_session(session_id)
        if existing is None:
            raise SessionNotFoundError(f"Session '{session_id}' not found")

        if existing.agent_id != agent_id:
            raise SessionBindingError(session_id, existing.agent_id, agent_id)

        target_tombstone = TerminalSessionTombstone(
            session_id=session_id,
            agent_id=agent_id,
            terminated_at=now,
            terminal_reason=TerminalReason.EXPLICIT_END,
        )
        if not self._session_repository.terminalize_session(
            session_id, target_tombstone
        ):
            # Race condition handling: re-verify tombstone under lock/concurrency
            recheck = self._session_repository.get_tombstone(session_id)
            if recheck is not None:
                if recheck.agent_id != agent_id:
                    raise SessionBindingError(session_id, recheck.agent_id, agent_id)
                return
            raise SessionNotFoundError(f"Session '{session_id}' not found")

    def expire_idle_sessions(
        self,
        idle_threshold_seconds: float,
        now_utc: datetime | None = None,
    ) -> list[str]:
        """Authoritative idle expiration: transition idle active sessions to TERMINAL."""
        if idle_threshold_seconds <= 0:
            raise ValueError("idle_threshold_seconds must be positive")

        now = now_utc or datetime.now(timezone.utc)
        expired_ids: list[str] = []

        for session in self._session_repository.list_sessions():
            elapsed = (now - session.last_activity_at).total_seconds()
            if elapsed >= idle_threshold_seconds:
                tombstone = TerminalSessionTombstone(
                    session_id=session.session_id,
                    agent_id=session.agent_id,
                    terminated_at=now,
                    terminal_reason=TerminalReason.IDLE_TIMEOUT,
                )
                if self._session_repository.terminalize_session(
                    session.session_id, tombstone
                ):
                    expired_ids.append(session.session_id)

        return expired_ids

    def is_terminal(self, session_id: str) -> bool:
        """Check if a session identifier is in terminal state."""
        return self._session_repository.get_tombstone(session_id) is not None

    def get_tombstone(self, session_id: str) -> TerminalSessionTombstone | None:
        """Retrieve the terminal tombstone for a session if it exists."""
        return self._session_repository.get_tombstone(session_id)

    def record_event(
        self,
        event: SessionEvent,
    ) -> SessionEvent:
        """Record a session event, strictly allocating sequence and persisting via repository."""
        recorded = self._session_repository.record_event(event)
        self._prune_events(now=recorded.timestamp)
        return recorded

    def _prune_events(self, now: datetime) -> int:
        """Prune expired session events whose timestamp is older than the retention cutoff."""
        if self._retention_policy is None:
            return 0

        cutoff = now - timedelta(seconds=self._retention_policy.total_retention_seconds)
        return self._session_repository.prune_events(cutoff=cutoff)

    def prune_events(self, now_utc: datetime | None = None) -> int:
        """Explicit maintenance trigger to prune expired events under the retention policy."""
        now = now_utc or datetime.now(timezone.utc)
        return self._prune_events(now)

    def list_events(
        self,
        session_id: str,
    ) -> list[SessionEvent]:
        """Return the session's events in canonical (timestamp, sequence_number) order."""
        return self._session_repository.list_events(session_id)

    def list_eligible_events(
        self,
        query: HorizonQuery,
    ) -> list[SessionEvent]:
        """Return defensive copies of events eligible for behavioral detection under the query specification."""
        return self._session_repository.list_eligible_events(query)

    def update_event_final_decision(
        self,
        session_id: str,
        sequence_number: int,
        final_decision: Decision,
    ) -> None:
        """Update the final_decision on an existing recorded session event in the repository."""
        self._session_repository.update_event_final_decision(
            session_id=session_id,
            sequence_number=sequence_number,
            final_decision=final_decision,
        )
