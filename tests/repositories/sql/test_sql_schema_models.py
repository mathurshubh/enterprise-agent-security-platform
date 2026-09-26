"""Verification test suite for Plane 3 SQLAlchemy persistence models and SQLite schema creation."""

from sqlalchemy import create_engine, inspect

from app.repositories.sql.base import Base
from app.repositories.sql.models import (
    AgentEnforcementStateModel,
    AgentEnforcementTransitionModel,
    AgentModel,
    AgentSequenceCounterModel,
    AuditEventModel,
    ExecutionGrantModel,
    SessionEventModel,
    SessionModel,
    ToolModel,
)


def test_sql_models_metadata_registration() -> None:
    """Verify that all domain persistence models are registered in Base.metadata."""
    models = [
        AgentModel,
        ToolModel,
        AgentEnforcementStateModel,
        AgentEnforcementTransitionModel,
        SessionModel,
        AgentSequenceCounterModel,
        SessionEventModel,
        ExecutionGrantModel,
        AuditEventModel,
    ]
    assert len(models) == 9
    table_names = set(Base.metadata.tables.keys())
    for model in models:
        assert model.__tablename__ in table_names



def test_sqlite_schema_creation_and_constraints() -> None:
    """Verify that Base.metadata can create all tables and constraints cleanly in SQLite."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    created_tables = set(inspector.get_table_names())
    expected_tables = {
        "agents",
        "tools",
        "agent_enforcement_state",
        "agent_enforcement_transitions",
        "sessions",
        "agent_sequence_counters",
        "session_events",
        "execution_grants",
        "audit_events",
    }
    assert expected_tables.issubset(created_tables)

    # 1. Verify session_events.final_decision is nullable
    session_event_cols = {
        col["name"]: col for col in inspector.get_columns("session_events")
    }
    assert session_event_cols["final_decision"]["nullable"] is True
    assert session_event_cols["decision"]["nullable"] is False
    assert session_event_cols["sequence_number"]["nullable"] is False
    assert session_event_cols["agent_sequence"]["nullable"] is False

    # 2. Verify sessions.last_activity_at exists and is nullable
    session_cols = {col["name"]: col for col in inspector.get_columns("sessions")}
    assert "last_activity_at" in session_cols
    assert session_cols["last_activity_at"]["nullable"] is True
    assert session_cols["created_at"]["nullable"] is False
    assert session_cols["updated_at"]["nullable"] is False

    # 3. Verify uniqueness constraints on session_events
    unique_constraints = inspector.get_unique_constraints("session_events")
    unique_col_sets = [set(u["column_names"]) for u in unique_constraints]
    assert {"session_id", "sequence_number"} in unique_col_sets
    assert {"agent_id", "agent_sequence"} in unique_col_sets

    # 4. Verify foreign keys
    session_fks = inspector.get_foreign_keys("sessions")
    assert any(fk["referred_table"] == "agents" for fk in session_fks)

    session_event_fks = inspector.get_foreign_keys("session_events")
    ref_tables = {fk["referred_table"] for fk in session_event_fks}
    assert {"sessions", "agents", "tools"}.issubset(ref_tables)
