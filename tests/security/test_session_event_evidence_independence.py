"""Finding 2: session events are evidence, not tool-registry references (ADR-034 §7).

Migration 0004 gave ``session_events`` foreign keys to ``tool_families`` and ``tools`` on
the premise that a refused event always names a registered family. The runtime records the
family a request *named*, before and regardless of its existence, so in SQL mode a request
for an unregistered tool was denied and then failed to record: ``IntegrityError`` instead of
a clean denial, and the denial lost from the evidence excessive-denial detection counts.

Migration 0007 removed the tool references. These tests pin both halves of the contract:
tool-registry membership is never a prerequisite for recording, and the integrity of the
event stream itself (ownership, sequencing) is still enforced by the database.

None of this concerns execution: an unknown tool is denied by authorization either way.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select

from app.models.audit_event import Decision
from app.repositories.sql.base import Base
from app.repositories.sql.engine import create_sql_engine, dispose_sql_engine
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.models.session_event import SessionEventModel
from app.repositories.sql.session import create_session_factory, transactional_session
from app.repositories.sql.session_repository import SqlSessionRepository
from app.services.detection_service import EXCESSIVE_DENIALS_RULE_NAME

UNKNOWN_TOOL = "tool-that-was-never-registered"


@pytest.fixture
def sql_engine():
    engine = create_sql_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    dispose_sql_engine(engine)


@pytest.fixture
def sql_runtime(build_runtime, sql_engine):
    """The security corpus pipeline with the SQL session repository in place of in-memory.

    Only the agent row is seeded, because session ownership is still a foreign key. No tool
    family or version is seeded: that is the point.
    """
    factory = create_session_factory(sql_engine)
    env = build_runtime(session_repository=SqlSessionRepository(factory))
    now = datetime.now(timezone.utc)
    with transactional_session(factory) as db:
        db.add(
            AgentModel(
                agent_id=env.agent_id,
                name="Corpus Agent",
                owner="security-team",
                risk_tier="HIGH",
                approved_tools=["file_read", "directory_list"],
                created_at=now,
                updated_at=now,
            )
        )
    env.session_factory = factory
    return env


@pytest.mark.security_invariant
def test_invariant_session_events_reference_ownership_and_never_the_tool_registry(
    sql_engine,
) -> None:
    """Both sides, so "remove tool FKs" cannot be read as "remove evidence integrity"."""
    inspector = inspect(sql_engine)

    referred = {fk["referred_table"] for fk in inspector.get_foreign_keys("session_events")}
    assert "tool_families" not in referred
    assert "tools" not in referred
    assert referred == {"sessions", "agents"}

    uniques = {
        u["name"]: tuple(u["column_names"])
        for u in inspector.get_unique_constraints("session_events")
    }
    assert uniques["uq_session_events_session_sequence"] == ("session_id", "sequence_number")
    assert uniques["uq_session_events_agent_sequence"] == ("agent_id", "agent_sequence")

    checks = {c["name"] for c in inspector.get_check_constraints("session_events")}
    assert {
        "chk_session_events_seq_positive",
        "chk_session_events_agent_seq_positive",
    } <= checks

    indexes = {i["name"] for i in inspector.get_indexes("session_events")}
    assert {
        "idx_session_events_agent_horizon",
        "idx_session_events_session_horizon",
        "idx_session_events_timestamp_prune",
    } <= indexes


@pytest.mark.security_regression
def test_unknown_tool_is_denied_cleanly_and_its_event_is_recorded_in_sql(sql_runtime) -> None:
    """The exact defect: this raised ``IntegrityError`` from ``record_event``."""
    result = sql_runtime.runtime.execute(
        session_id="sess-unknown-tool",
        agent_id=sql_runtime.agent_id,
        tool_id=UNKNOWN_TOOL,
    )

    assert result.event.decision == Decision.DENY
    assert result.authorization is None, "an unknown tool must never receive execution authority"

    with transactional_session(sql_runtime.session_factory) as db:
        rows = db.execute(
            select(SessionEventModel).where(SessionEventModel.session_id == "sess-unknown-tool")
        ).scalars().all()
    assert [(r.tool_id, r.tool_version, r.decision) for r in rows] == [
        (UNKNOWN_TOOL, None, "DENY")
    ]


@pytest.mark.security_regression
def test_unknown_tool_denials_reach_excessive_denial_detection_in_sql(sql_runtime) -> None:
    """The security consequence: unrecordable denials were invisible to detection.

    Probing for tools that do not exist is exactly the activity that produces these denials.
    """
    session_id = "sess-tool-probing"
    for probe in range(3):
        result = sql_runtime.runtime.execute(
            session_id=session_id,
            agent_id=sql_runtime.agent_id,
            tool_id=f"{UNKNOWN_TOOL}-{probe}",
        )
        assert result.event.decision == Decision.DENY
        assert result.authorization is None

    findings = sql_runtime.findings_service.list_findings(
        session_id=session_id, agent_id=sql_runtime.agent_id
    )
    excessive = [f for f in findings if f.rule_name == EXCESSIVE_DENIALS_RULE_NAME]
    assert len(excessive) == 1
    assert excessive[0].evidence_event_sequences, "the finding must cite the recorded denials"
