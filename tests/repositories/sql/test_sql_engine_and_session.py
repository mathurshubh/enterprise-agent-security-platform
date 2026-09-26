"""Unit tests for SQL engine factory and transactional session management (Plane 3)."""

from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.repositories.sql.base import Base
from app.repositories.sql.engine import create_sql_engine, dispose_sql_engine
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.models.session import SessionModel
from app.repositories.sql.session import create_session_factory, transactional_session


@pytest.fixture
def memory_engine() -> Generator:
    """Fixture providing an in-memory SQLite engine with foreign key enforcement."""
    engine = create_sql_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    dispose_sql_engine(engine)


def test_sqlite_foreign_keys_pragma_enforced(memory_engine) -> None:
    """Verify that foreign key constraints are actively enforced in SQLite connections."""
    with memory_engine.connect() as conn:
        result = conn.execute(text("PRAGMA foreign_keys;")).scalar()
        assert result == 1


def test_sqlite_foreign_key_violation_raises_integrity_error(memory_engine) -> None:
    """Verify inserting a session referencing a nonexistent agent fails foreign key check."""
    session_factory = create_session_factory(memory_engine)
    now = datetime.now(timezone.utc)

    # Attempting to insert a session with nonexistent agent_id must fail
    with pytest.raises(IntegrityError):
        with transactional_session(session_factory) as session:
            invalid_session = SessionModel(
                session_id="sess-orphan",
                agent_id="nonexistent-agent",
                status="ACTIVE",
                next_session_sequence=1,
                created_at=now,
                updated_at=now,
            )
            session.add(invalid_session)


def test_transactional_session_commits_on_success(memory_engine) -> None:
    """Verify that operations inside transactional_session are committed upon normal exit."""
    session_factory = create_session_factory(memory_engine)
    now = datetime.now(timezone.utc)

    with transactional_session(session_factory) as session:
        agent = AgentModel(
            agent_id="agent-001",
            name="FinanceAgent",
            owner="secops@enterprise.internal",
            risk_tier="HIGH",
            status="ACTIVE",
            approved_tools=["tool_a"],
            created_at=now,
            updated_at=now,
        )
        session.add(agent)

    # Verify agent was committed and is visible in a new session
    with transactional_session(session_factory) as session:
        persisted = session.get(AgentModel, "agent-001")
        assert persisted is not None
        assert persisted.name == "FinanceAgent"
        assert persisted.owner == "secops@enterprise.internal"


def test_transactional_session_rolls_back_on_exception(memory_engine) -> None:
    """Verify that exceptions inside transactional_session trigger rollback."""
    session_factory = create_session_factory(memory_engine)
    now = datetime.now(timezone.utc)

    with pytest.raises(RuntimeError, match="Simulated application error"):
        with transactional_session(session_factory) as session:
            agent = AgentModel(
                agent_id="agent-aborted",
                name="AbortedAgent",
                owner="secops@enterprise.internal",
                risk_tier="LOW",
                status="ACTIVE",
                approved_tools=[],
                created_at=now,
                updated_at=now,
            )
            session.add(agent)
            raise RuntimeError("Simulated application error")

    # Verify agent was not persisted
    with transactional_session(session_factory) as session:
        assert session.get(AgentModel, "agent-aborted") is None


def test_transactional_session_with_existing_session(memory_engine) -> None:
    """Verify transactional_session accepts an existing Session without closing it."""
    session_factory = create_session_factory(memory_engine)
    now = datetime.now(timezone.utc)

    external_session = session_factory()
    try:
        with transactional_session(external_session) as session:
            assert session is external_session
            agent = AgentModel(
                agent_id="agent-nested",
                name="NestedAgent",
                owner="secops@enterprise.internal",
                risk_tier="LOW",
                status="ACTIVE",
                approved_tools=[],
                created_at=now,
                updated_at=now,
            )
            session.add(agent)

        # External session should remain open and valid
        assert external_session.is_active
        persisted = external_session.get(AgentModel, "agent-nested")
        assert persisted is not None
    finally:
        external_session.close()


def test_engine_disposal(memory_engine) -> None:
    """Verify dispose_sql_engine successfully disposes engine resources."""
    dispose_sql_engine(memory_engine)
    # Reconnecting should work as SQLite re-establishes or reinitializes
    with memory_engine.connect() as conn:
        result = conn.execute(text("SELECT 1;")).scalar()
        assert result == 1
