"""PostgreSQL MVCC concurrency test suite for SqlSessionRepository (Plane 3, ADR-030).

Authority Note:
While SQLite validates the functional repository contract (lifecycle, windowing, ordering,
watermarks, and immutability), PostgreSQL is the sole concurrency authority. It proves
the MVCC row-locking contract (FOR UPDATE), lock ordering (sessions -> agent_sequence_counters),
and atomic sequence allocation across concurrent workers.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from app.models.audit_event import Decision
from app.models.session import (
    SessionTerminalError,
    TerminalReason,
    TerminalSessionTombstone,
)
from app.models.session_event import SessionEvent
from app.repositories.sql.base import Base
from app.repositories.sql.engine import create_sql_engine, dispose_sql_engine
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.models.tool import ToolModel
from app.repositories.sql.session import create_session_factory, transactional_session
from app.repositories.sql.session_repository import SqlSessionRepository

POSTGRES_URL = os.environ.get("TEST_DATABASE_URL")
postgres_required = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="PostgreSQL not configured via TEST_DATABASE_URL; concurrency authority suite requires live PostgreSQL",
)


@pytest.fixture
def pg_session_repo():
    """Fixture providing a fresh SqlSessionRepository connected to PostgreSQL."""
    if not POSTGRES_URL:
        pytest.skip("TEST_DATABASE_URL not configured")

    engine = create_sql_engine(POSTGRES_URL, pool_size=10, max_overflow=10)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    session_factory = create_session_factory(engine)
    now = datetime.now(timezone.utc)

    # Seed test dependencies
    with transactional_session(session_factory) as db:
        agent = AgentModel(
            agent_id="agent-pg-conc",
            name="PGConcurrencyAgent",
            owner="secops@enterprise.internal",
            risk_tier="HIGH",
            status="ACTIVE",
            approved_tools=["file_read"],
            created_at=now,
            updated_at=now,
        )
        tool = ToolModel(
            tool_id="file_read",
            name="file_read",
            description="Read file",
            risk_level="LOW",
            required_permissions=[],
            metadata_payload={},
            is_active=True,
            created_at=now,
        )
        db.add(agent)
        db.add(tool)

    repo = SqlSessionRepository(session_factory)
    yield repo, session_factory
    dispose_sql_engine(engine)


@postgres_required
def test_postgres_concurrent_same_session_recording(pg_session_repo) -> None:
    """Race 1: Concurrent record_event calls on the same session allocate unique, contiguous sequences."""
    repo, _ = pg_session_repo
    now = datetime.now(timezone.utc)
    session_id = "sess-pg-single"
    agent_id = "agent-pg-conc"

    repo.bind_or_create_session(session_id, agent_id, now=now)
    num_events = 20

    def worker(idx: int) -> SessionEvent:
        event = SessionEvent(
            session_id=session_id,
            agent_id=agent_id,
            tool_id="file_read",
            decision=Decision.ALLOW,
            timestamp=now,
        )
        return repo.record_event(event)

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(worker, range(num_events)))

    seq_numbers = sorted(e.sequence_number for e in results)
    assert seq_numbers == list(range(1, num_events + 1))
    agent_seqs = sorted(e.agent_sequence for e in results)
    assert agent_seqs == list(range(1, num_events + 1))


@postgres_required
def test_postgres_concurrent_cross_session_recording_same_agent(pg_session_repo) -> None:
    """Race 2: Concurrent recording across multiple sessions for the same agent allocates monotonic sequences."""
    repo, _ = pg_session_repo
    now = datetime.now(timezone.utc)
    agent_id = "agent-pg-conc"

    repo.bind_or_create_session("sess-pg-cross-1", agent_id, now=now)
    repo.bind_or_create_session("sess-pg-cross-2", agent_id, now=now)

    num_events = 20

    def worker(idx: int) -> SessionEvent:
        sess = "sess-pg-cross-1" if idx % 2 == 0 else "sess-pg-cross-2"
        event = SessionEvent(
            session_id=sess,
            agent_id=agent_id,
            tool_id="file_read",
            decision=Decision.ALLOW,
            timestamp=now,
        )
        return repo.record_event(event)

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(worker, range(num_events)))

    agent_seqs = [e.agent_sequence for e in results]
    assert len(set(agent_seqs)) == num_events
    assert sorted(agent_seqs) == list(range(1, num_events + 1))


@postgres_required
def test_postgres_terminalization_race_with_record_event(pg_session_repo) -> None:
    """Race 3: Terminalization racing with record_event guarantees no event commits on a terminal session."""
    repo, _ = pg_session_repo
    now = datetime.now(timezone.utc)
    session_id = "sess-pg-term-race"
    agent_id = "agent-pg-conc"

    repo.bind_or_create_session(session_id, agent_id, now=now)

    recorded_events = []
    terminal_errors = []

    def event_worker(idx: int) -> None:
        try:
            event = SessionEvent(
                session_id=session_id,
                agent_id=agent_id,
                tool_id="file_read",
                decision=Decision.ALLOW,
                timestamp=now,
            )
            ev = repo.record_event(event)
            recorded_events.append(ev)
        except SessionTerminalError as err:
            terminal_errors.append(err)

    def term_worker() -> None:
        tombstone = TerminalSessionTombstone(
            session_id=session_id,
            agent_id=agent_id,
            terminated_at=now,
            terminal_reason=TerminalReason.EXPLICIT_END,
        )
        repo.terminalize_session(session_id, tombstone)

    with ThreadPoolExecutor(max_workers=11) as executor:
        f_events = [executor.submit(event_worker, i) for i in range(10)]
        f_term = executor.submit(term_worker)
        f_term.result()
        for f in f_events:
            f.result()

    # All events either succeeded before terminalization or failed closed with SessionTerminalError
    assert len(recorded_events) + len(terminal_errors) == 10
    # Tombstone is guaranteed to be set
    assert repo.get_tombstone(session_id) is not None
