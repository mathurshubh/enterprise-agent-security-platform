"""SQL implementation of SessionRepository unifying lifecycle and detection horizon (Plane 3, ADR-030)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.models.audit_event import Decision
from app.models.session import (
    Session,
    SessionAlreadyExistsError,
    SessionBindingError,
    SessionNotFoundError,
    SessionRepositoryError,
    SessionTerminalError,
    TerminalReason,
    TerminalSessionTombstone,
)
from app.models.session_event import (
    AggregationScope,
    HorizonQuery,
    SessionEvent,
)
from app.repositories.interfaces.session_repository import SessionRepository
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.models.session import AgentSequenceCounterModel, SessionModel
from app.repositories.sql.models.session_event import SessionEventModel
from app.repositories.sql.session import transactional_session


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Ensure a datetime returned from the database has timezone.utc attached."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class SqlSessionRepository(SessionRepository):
    """SQLAlchemy implementation of SessionRepository unifying session lifecycle and detection horizon.

    Invariants:
    - Object Isolation: Stored and returned entities are defensive domain models.
    - Preserved Identity: Terminalization transitions lifecycle status to 'TERMINAL' and persists
      tombstone metadata (ended_at, ended_reason). The row is permanently retained to preserve
      foreign-key referential integrity for historic events and execution grants.
    - Atomic Terminalization: terminalize_session atomically transitions the session to terminal
      under a row lock (FOR UPDATE).
    - Lock Ordering Invariant:
        1. sessions row (SessionModel)
        2. agent_sequence_counters row (AgentSequenceCounterModel)
      All transaction paths acquiring multiple entity locks must acquire them in this strict order
      to guarantee deadlock-free execution.
    - Strictly Increasing Dual Sequence Allocation: record_event atomically validates active session
      ownership, allocates the next session-level sequence_number, allocates the next agent-level
      agent_sequence, updates last_activity_at, and persists the event under a single atomic transaction.
    - Total Transaction Rollback: A failure at any point inside record_event aborts the entire transaction;
      no sequence counters are advanced, last_activity_at is unchanged, and no event is inserted.
    - Deterministic Horizon Ordering:
        scope == AGENT queries order by agent_sequence ASC.
        scope == SESSION queries order by sequence_number ASC.
    - Decision Finalization Immutability: update_event_final_decision allows None -> Decision and
      permits idempotent updates to the same decision, but strictly rejects mutations from an
      already-finalized decision to a different decision. Fails with SessionTerminalError if terminal.
    - Sequence Retention Independence: Event pruning never renumbers surviving events or resets sequence counters.
    """

    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    def get_session(self, session_id: str) -> Session | None:
        with transactional_session(self._session_factory) as db:
            row = db.execute(
                select(SessionModel).where(
                    SessionModel.session_id == session_id,
                    SessionModel.status == "ACTIVE",
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return Session(
                session_id=row.session_id,
                agent_id=row.agent_id,
                started_at=_ensure_utc(row.created_at),
                last_activity_at=_ensure_utc(row.last_activity_at or row.created_at),
            )

    def save_session(self, session: Session) -> None:
        with transactional_session(self._session_factory) as db:
            row = db.execute(
                select(SessionModel)
                .where(SessionModel.session_id == session.session_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is not None:
                row.agent_id = session.agent_id
                row.created_at = session.started_at
                row.last_activity_at = session.last_activity_at
                row.updated_at = datetime.now(timezone.utc)
            else:
                new_row = SessionModel(
                    session_id=session.session_id,
                    agent_id=session.agent_id,
                    status="ACTIVE",
                    next_session_sequence=1,
                    created_at=session.started_at,
                    last_activity_at=session.last_activity_at,
                )
                db.add(new_row)

    def list_sessions(self) -> list[Session]:
        with transactional_session(self._session_factory) as db:
            rows = db.execute(
                select(SessionModel).where(SessionModel.status == "ACTIVE")
            ).scalars().all()
            return [
                Session(
                    session_id=r.session_id,
                    agent_id=r.agent_id,
                    started_at=_ensure_utc(r.created_at),
                    last_activity_at=_ensure_utc(r.last_activity_at or r.created_at),
                )
                for r in rows
            ]

    def create_session(self, session: Session) -> Session:
        with transactional_session(self._session_factory) as db:
            row = db.execute(
                select(SessionModel)
                .where(SessionModel.session_id == session.session_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is not None:
                if row.status == "TERMINAL":
                    raise SessionTerminalError(
                        session.session_id,
                        row.agent_id,
                        session.agent_id,
                    )
                raise SessionAlreadyExistsError(
                    f"Session '{session.session_id}' already exists"
                )
            new_row = SessionModel(
                session_id=session.session_id,
                agent_id=session.agent_id,
                status="ACTIVE",
                next_session_sequence=1,
                created_at=session.started_at,
                last_activity_at=session.last_activity_at,
            )
            db.add(new_row)
            return session.model_copy(deep=True)

    def bind_or_create_session(
        self,
        session_id: str,
        agent_id: str,
        *,
        now: datetime,
    ) -> Session:
        with transactional_session(self._session_factory) as db:
            row = db.execute(
                select(SessionModel)
                .where(SessionModel.session_id == session_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is not None:
                if row.status == "TERMINAL":
                    raise SessionTerminalError(session_id, row.agent_id, agent_id)
                if row.agent_id != agent_id:
                    raise SessionBindingError(session_id, row.agent_id, agent_id)
                row.last_activity_at = now
                row.updated_at = datetime.now(timezone.utc)
                return Session(
                    session_id=row.session_id,
                    agent_id=row.agent_id,
                    started_at=_ensure_utc(row.created_at),
                    last_activity_at=now,
                )
            new_row = SessionModel(
                session_id=session_id,
                agent_id=agent_id,
                status="ACTIVE",
                next_session_sequence=1,
                created_at=now,
                last_activity_at=now,
            )
            db.add(new_row)
            return Session(
                session_id=session_id,
                agent_id=agent_id,
                started_at=now,
                last_activity_at=now,
            )

    def get_tombstone(self, session_id: str) -> TerminalSessionTombstone | None:
        with transactional_session(self._session_factory) as db:
            row = db.execute(
                select(SessionModel).where(
                    SessionModel.session_id == session_id,
                    SessionModel.status == "TERMINAL",
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            reason = (
                TerminalReason(row.ended_reason)
                if row.ended_reason and row.ended_reason in TerminalReason.__members__
                else TerminalReason.EXPLICIT_END
            )
            return TerminalSessionTombstone(
                session_id=row.session_id,
                agent_id=row.agent_id,
                terminated_at=_ensure_utc(row.ended_at or row.updated_at),
                terminal_reason=reason,
            )

    def terminalize_session(
        self,
        session_id: str,
        tombstone: TerminalSessionTombstone,
    ) -> bool:
        with transactional_session(self._session_factory) as db:
            row = db.execute(
                select(SessionModel)
                .where(SessionModel.session_id == session_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.status == "TERMINAL":
                return False
            row.status = "TERMINAL"
            row.ended_at = tombstone.terminated_at
            row.ended_reason = (
                tombstone.terminal_reason.value
                if hasattr(tombstone.terminal_reason, "value")
                else str(tombstone.terminal_reason)
            )
            row.updated_at = datetime.now(timezone.utc)
            return True

    def record_event(self, event: SessionEvent) -> SessionEvent:
        if event.sequence_number != 0:
            raise ValueError(
                f"Cannot record event with caller-supplied sequence_number={event.sequence_number}; "
                "sequence allocation is strictly repository-owned."
            )
        if event.agent_sequence != 0:
            raise ValueError(
                f"Cannot record event with caller-supplied agent_sequence={event.agent_sequence}; "
                "sequence allocation is strictly repository-owned."
            )

        with transactional_session(self._session_factory) as db:
            # Lock Ordering Invariant: 1. Lock session row first
            session_row = db.execute(
                select(SessionModel)
                .where(SessionModel.session_id == event.session_id)
                .with_for_update()
            ).scalar_one_or_none()

            if session_row is None:
                raise SessionNotFoundError(
                    f"Session '{event.session_id}' not found; cannot record event for nonexistent session"
                )
            if session_row.status == "TERMINAL":
                raise SessionTerminalError(
                    event.session_id,
                    session_row.agent_id,
                    event.agent_id,
                )
            if session_row.agent_id != event.agent_id:
                raise SessionBindingError(
                    event.session_id,
                    session_row.agent_id,
                    event.agent_id,
                )

            # Allocate session sequence position
            next_session_seq = session_row.next_session_sequence
            session_row.next_session_sequence += 1
            session_row.last_activity_at = event.timestamp
            session_row.updated_at = datetime.now(timezone.utc)

            # Lock Ordering Invariant: 2. Lock parent agent row
            # Serializes counter creation/updates across concurrent sessions for the same agent
            db.execute(
                select(AgentModel)
                .where(AgentModel.agent_id == event.agent_id)
                .with_for_update()
            ).scalar_one_or_none()

            # Lock Ordering Invariant: 3. Lock/create agent counter
            counter = db.execute(
                select(AgentSequenceCounterModel)
                .where(AgentSequenceCounterModel.agent_id == event.agent_id)
                .with_for_update()
            ).scalar_one_or_none()

            if counter is None:
                counter = AgentSequenceCounterModel(
                    agent_id=event.agent_id,
                    current_sequence=1,
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(counter)
                next_agent_seq = 1
            else:
                counter.current_sequence += 1
                counter.updated_at = datetime.now(timezone.utc)
                next_agent_seq = counter.current_sequence

            # Insert session event
            event_row = SessionEventModel(
                event_id=f"evt-{uuid4()}",
                session_id=event.session_id,
                agent_id=event.agent_id,
                tool_id=event.tool_id,
                sequence_number=next_session_seq,
                agent_sequence=next_agent_seq,
                decision=(
                    event.decision.value
                    if isinstance(event.decision, Decision)
                    else str(event.decision)
                ),
                final_decision=(
                    event.final_decision.value
                    if isinstance(event.final_decision, Decision)
                    else (str(event.final_decision) if event.final_decision else None)
                ),
                timestamp=event.timestamp,
                created_at=datetime.now(timezone.utc),
            )
            db.add(event_row)

        return SessionEvent(
            session_id=event_row.session_id,
            agent_id=event_row.agent_id,
            tool_id=event_row.tool_id,
            sequence_number=event_row.sequence_number,
            agent_sequence=event_row.agent_sequence,
            decision=Decision(event_row.decision),
            final_decision=Decision(event_row.final_decision) if event_row.final_decision else None,
            timestamp=_ensure_utc(event_row.timestamp),
        )

    def list_eligible_events(self, query: HorizonQuery) -> list[SessionEvent]:
        try:
            cutoff = query.evaluation_time - timedelta(seconds=query.window_seconds)
            with transactional_session(self._session_factory) as db:
                stmt = select(SessionEventModel).where(
                    SessionEventModel.agent_id == query.agent_id,
                    SessionEventModel.agent_sequence > query.baseline_agent_sequence,
                    SessionEventModel.timestamp >= cutoff,
                    SessionEventModel.timestamp <= query.evaluation_time,
                )
                if query.scope == AggregationScope.SESSION:
                    stmt = stmt.where(SessionEventModel.session_id == query.session_id)
                    stmt = stmt.order_by(SessionEventModel.sequence_number.asc())
                else:
                    stmt = stmt.order_by(SessionEventModel.agent_sequence.asc())

                rows = db.execute(stmt).scalars().all()
                return [
                    SessionEvent(
                        session_id=r.session_id,
                        agent_id=r.agent_id,
                        tool_id=r.tool_id,
                        sequence_number=r.sequence_number,
                        agent_sequence=r.agent_sequence,
                        decision=Decision(r.decision),
                        final_decision=Decision(r.final_decision) if r.final_decision else None,
                        timestamp=_ensure_utc(r.timestamp),
                    )
                    for r in rows
                ]
        except Exception as exc:
            if isinstance(exc, SessionRepositoryError):
                raise
            raise SessionRepositoryError(f"Failed to query eligible events: {exc}") from exc

    def list_events(self, session_id: str) -> list[SessionEvent]:
        with transactional_session(self._session_factory) as db:
            rows = db.execute(
                select(SessionEventModel)
                .where(SessionEventModel.session_id == session_id)
                .order_by(
                    SessionEventModel.timestamp.asc(),
                    SessionEventModel.sequence_number.asc(),
                )
            ).scalars().all()
            return [
                SessionEvent(
                    session_id=r.session_id,
                    agent_id=r.agent_id,
                    tool_id=r.tool_id,
                    sequence_number=r.sequence_number,
                    agent_sequence=r.agent_sequence,
                    decision=Decision(r.decision),
                    final_decision=Decision(r.final_decision) if r.final_decision else None,
                    timestamp=_ensure_utc(r.timestamp),
                )
                for r in rows
            ]

    def prune_events(self, *, cutoff: datetime) -> int:
        with transactional_session(self._session_factory) as db:
            result = db.execute(
                delete(SessionEventModel).where(SessionEventModel.timestamp < cutoff)
            )
            return int(result.rowcount)

    def update_event_final_decision(
        self,
        session_id: str,
        sequence_number: int,
        final_decision: Decision,
    ) -> None:
        with transactional_session(self._session_factory) as db:
            # Lock Ordering Invariant: 1. Lock session row first
            session_row = db.execute(
                select(SessionModel)
                .where(SessionModel.session_id == session_id)
                .with_for_update()
            ).scalar_one_or_none()

            if session_row is None:
                raise SessionNotFoundError(f"Session '{session_id}' not found")
            if session_row.status == "TERMINAL":
                raise SessionTerminalError(session_id, session_row.agent_id, session_row.agent_id)

            event_row = db.execute(
                select(SessionEventModel)
                .where(
                    SessionEventModel.session_id == session_id,
                    SessionEventModel.sequence_number == sequence_number,
                )
                .with_for_update()
            ).scalar_one_or_none()

            if event_row is None:
                raise ValueError(
                    f"Event with sequence {sequence_number} not found for session '{session_id}'"
                )

            if event_row.final_decision is not None:
                current = Decision(event_row.final_decision)
                if current != final_decision:
                    raise ValueError(
                        f"Event {sequence_number} in session '{session_id}' is already finalized "
                        f"as {current} and cannot transition to {final_decision}"
                    )
                return

            event_row.final_decision = (
                final_decision.value if isinstance(final_decision, Decision) else str(final_decision)
            )
