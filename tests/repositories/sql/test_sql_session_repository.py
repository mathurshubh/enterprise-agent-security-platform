"""Verification and contract tests for SqlSessionRepository (Plane 3, ADR-030)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.audit_event import Decision
from app.models.session import (
    SessionTerminalError,
    TerminalReason,
    TerminalSessionTombstone,
)
from app.models.session_event import SessionEvent
from app.repositories.interfaces.session_repository import SessionRepository
from app.repositories.sql.base import Base
from app.repositories.sql.engine import create_sql_engine, dispose_sql_engine
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.models.session import AgentSequenceCounterModel, SessionModel
from app.repositories.sql.models.session_event import SessionEventModel
from app.repositories.sql.models.tool import ToolModel
from app.repositories.sql.session import create_session_factory, transactional_session
from app.repositories.sql.session_repository import SqlSessionRepository, _ensure_utc
from tests.repositories.contracts.base_session_contract import (
    BaseSessionRepositoryContractTests,
)

KNOWN_CONTRACT_AGENTS = [
    "agent-1",
    "agent-2",
    "agent-a",
    "agent-b",
    "agent-concurrent-seq",
    "agent-gapless",
    "agent-immut",
    "agent-intruder",
    "agent-owner",
    "agent-pw",
    "agent-race",
    "tampered-agent",
    "test-agent",
]

KNOWN_CONTRACT_TOOLS = [
    "file_read",
    "shell_exec",
]


def _seed_test_dependencies(session_factory) -> None:
    """Explicitly provision known test agents and tools in the database fixtures."""
    now = datetime.now(timezone.utc)
    with transactional_session(session_factory) as db:
        for agent_id in KNOWN_CONTRACT_AGENTS:
            db.merge(
                AgentModel(
                    agent_id=agent_id,
                    name=agent_id,
                    owner="secops@enterprise.internal",
                    risk_tier="LOW",
                    status="ACTIVE",
                    approved_tools=KNOWN_CONTRACT_TOOLS,
                    created_at=now,
                    updated_at=now,
                )
            )
        for tool_id in KNOWN_CONTRACT_TOOLS:
            db.merge(
                ToolModel(
                    tool_id=tool_id,
                    name=tool_id,
                    description=f"Test fixture tool {tool_id}",
                    risk_level="LOW",
                    required_permissions=[],
                    metadata_payload={},
                    is_active=True,
                    created_at=now,
                )
            )


class TestSqlSessionRepository(BaseSessionRepositoryContractTests):
    """Run the exhaustive Plane 2/3 session contract suite against SqlSessionRepository.

    Architecture Note:
    SQLite validates the functional repository contract (lifecycle, watermark, windowing,
    ordering, immutability, pruning). Real multi-worker MVCC row-locking concurrency
    (FOR UPDATE) is the exclusive domain of PostgreSQL. The four concurrency contract tests
    are verified under the PostgreSQL concurrency harness.
    """

    def create_repository(self) -> SessionRepository:
        """Create a fresh in-memory SQLite database, run schema creation, seed fixture dependencies."""
        engine = create_sql_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session_factory = create_session_factory(engine)
        _seed_test_dependencies(session_factory)
        return SqlSessionRepository(session_factory)

    @pytest.mark.skip(
        reason=(
            "Concurrency contract authority requires PostgreSQL FOR UPDATE semantics. "
            "SQLite dialect does not implement row-level locking (with_for_update is a no-op in SQLite); "
            "multi-worker serialization is tested in test_sql_session_concurrency_postgres.py."
        )
    )
    def test_concurrent_session_binding(self) -> None:
        super().test_concurrent_session_binding()

    @pytest.mark.skip(
        reason=(
            "Concurrency contract authority requires PostgreSQL FOR UPDATE semantics. "
            "SQLite dialect does not implement row-level locking (with_for_update is a no-op in SQLite); "
            "concurrent sequence allocation is tested in test_sql_session_concurrency_postgres.py."
        )
    )
    def test_concurrent_event_recording_allocates_unique_sequences(self) -> None:
        super().test_concurrent_event_recording_allocates_unique_sequences()

    @pytest.mark.skip(
        reason=(
            "Concurrency contract authority requires PostgreSQL FOR UPDATE semantics. "
            "SQLite dialect does not implement row-level locking (with_for_update is a no-op in SQLite); "
            "concurrent agent sequence allocation is tested in test_sql_session_concurrency_postgres.py."
        )
    )
    def test_concurrent_record_event_allocates_unique_agent_sequences(self) -> None:
        super().test_concurrent_record_event_allocates_unique_agent_sequences()

    @pytest.mark.skip(
        reason=(
            "Concurrency contract authority requires PostgreSQL FOR UPDATE semantics. "
            "SQLite dialect does not implement row-level locking (with_for_update is a no-op in SQLite); "
            "terminalization race serialization is tested in test_sql_session_concurrency_postgres.py."
        )
    )
    def test_terminalization_races_with_record_event(self) -> None:
        super().test_terminalization_races_with_record_event()


@pytest.fixture
def sql_repo_setup():
    """Fixture providing a configured SqlSessionRepository and session factory."""
    engine = create_sql_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    _seed_test_dependencies(session_factory)
    repo = SqlSessionRepository(session_factory)
    yield repo, session_factory
    dispose_sql_engine(engine)


def test_atomic_rollback_on_failed_event_record(sql_repo_setup) -> None:
    """Verify failure during record_event rolls back session sequence, agent counter, and activity.

    Invariant:
    A failure at any point must produce:
    - NO session sequence advancement
    - NO agent sequence advancement
    - NO last_activity_at mutation
    - NO session event inserted
    """
    repo, session_factory = sql_repo_setup
    now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    later = datetime(2026, 9, 26, 12, 5, 0, tzinfo=timezone.utc)

    # 1. Create active session
    session = repo.bind_or_create_session("sess-atomic", "agent-1", now=now)
    assert session.last_activity_at == now

    # 2. Record one successful event
    ev1 = SessionEvent(
        session_id="sess-atomic",
        agent_id="agent-1",
        tool_id="file_read",
        decision=Decision.ALLOW,
        timestamp=now,
    )
    recorded1 = repo.record_event(ev1)
    assert recorded1.sequence_number == 1
    assert recorded1.agent_sequence == 1

    # 3. Attempt to record an event referencing an unregistered tool (fails FK constraint)
    invalid_event = SessionEvent(
        session_id="sess-atomic",
        agent_id="agent-1",
        tool_id="unregistered-foreign-tool",
        decision=Decision.ALLOW,
        timestamp=later,
    )

    with pytest.raises(IntegrityError):
        repo.record_event(invalid_event)

    # 4. Verify invariants in storage:
    with transactional_session(session_factory) as db:
        # Session row must NOT have advanced sequence and must NOT have updated last_activity_at
        s_row = db.execute(
            select(SessionModel).where(SessionModel.session_id == "sess-atomic")
        ).scalar_one()
        assert s_row.next_session_sequence == 2  # Still 2 (for next event), did not advance to 3
        assert _ensure_utc(s_row.last_activity_at) == now  # Still original timestamp, did not mutate

        # Agent counter must NOT have advanced
        c_row = db.execute(
            select(AgentSequenceCounterModel).where(AgentSequenceCounterModel.agent_id == "agent-1")
        ).scalar_one()
        assert c_row.current_sequence == 1  # Still 1, did not advance to 2

        # Session events must only contain 1 event
        events = db.execute(
            select(SessionEventModel).where(SessionEventModel.session_id == "sess-atomic")
        ).scalars().all()
        assert len(events) == 1
        assert events[0].sequence_number == 1


def test_strict_foreign_key_enforcement_unknown_agent(sql_repo_setup) -> None:
    """Verify that creating a session for an unknown agent fails closed with IntegrityError."""
    repo, _ = sql_repo_setup
    now = datetime.now(timezone.utc)

    with pytest.raises(IntegrityError):
        repo.bind_or_create_session("sess-unknown", "unknown-agent-id", now=now)


def test_terminalization_event_race_rejection(sql_repo_setup) -> None:
    """Verify that once a session is terminalized, subsequent record_event fails closed."""
    repo, _ = sql_repo_setup
    now = datetime.now(timezone.utc)

    repo.bind_or_create_session("sess-term-race", "agent-1", now=now)
    tombstone = TerminalSessionTombstone(
        session_id="sess-term-race",
        agent_id="agent-1",
        terminated_at=now,
        terminal_reason=TerminalReason.EXPLICIT_END,
    )
    assert repo.terminalize_session("sess-term-race", tombstone) is True

    ev = SessionEvent(
        session_id="sess-term-race",
        agent_id="agent-1",
        tool_id="file_read",
        decision=Decision.ALLOW,
        timestamp=now,
    )
    with pytest.raises(SessionTerminalError):
        repo.record_event(ev)
