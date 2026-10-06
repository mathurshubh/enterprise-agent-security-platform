"""Verification and contract tests for SqlToolRepository (Plane 3, ADR-030)."""

from sqlalchemy import inspect, select

from app.models.tool_risk_level import ToolRiskLevel
from app.repositories.interfaces.tool_repository import ToolRepository
from app.repositories.sql.base import Base
from app.repositories.sql.engine import create_sql_engine
from app.repositories.sql.models.session_event import SessionEventModel
from app.repositories.sql.models.tool import ToolFamilyModel, ToolModel
from app.repositories.sql.session import create_session_factory, transactional_session
from app.repositories.sql.tool_repository import SqlToolRepository
from tests.repositories.contracts.base_tool_contract import (
    BaseToolRepositoryContractTests,
)


def _tool(tool_id: str, version: str):
    """The contract suite's fully-populated fixture, reused for adapter-specific tests."""
    return BaseToolRepositoryContractTests._fully_populated_tool(tool_id, version)


def _factory():
    engine = create_sql_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


class TestSqlToolRepository(BaseToolRepositoryContractTests):
    """Hold the SQL adapter to the same contract as the in-memory one.

    The two adapters diverging is the defect class this suite exists to prevent: the
    in-memory repository has been keyed ``(tool_id, version)`` since Slice 1a while the
    durable table was keyed by family alone, and nothing held them to one contract because
    only the in-memory adapter ran it.
    """

    def create_repository(self) -> ToolRepository:
        return SqlToolRepository(_factory())


class TestSqlToolRepositoryPersistenceShape:
    """Adapter-specific behaviour the generic contract cannot express."""

    def test_the_family_anchor_is_created_from_the_version_save(self) -> None:
        """There is no create_family operation; a version save is what materialises one."""
        factory = _factory()
        repo = SqlToolRepository(factory)

        repo.save(_tool("file_read", "1.0.0"))

        with transactional_session(factory) as db:
            families = db.execute(select(ToolFamilyModel.tool_id)).scalars().all()
        assert families == ["file_read"]

    def test_two_versions_share_one_family_row(self) -> None:
        factory = _factory()
        repo = SqlToolRepository(factory)
        repo.save(_tool("file_read", "1.0.0"))
        repo.save(_tool("file_read", "2.0.0"))

        with transactional_session(factory) as db:
            families = db.execute(select(ToolFamilyModel.tool_id)).scalars().all()
            versions = db.execute(select(ToolModel.version).order_by(ToolModel.version)).scalars().all()

        assert families == ["file_read"], "the family is an anchor, not one row per version"
        assert versions == ["1.0.0", "2.0.0"]

    def test_projections_are_written_from_the_payload(self) -> None:
        """``governance_enabled`` and ``risk_level`` describe the row they are stored on."""
        factory = _factory()
        repo = SqlToolRepository(factory)
        tool = _tool("file_read", "1.0.0")

        repo.save(tool)

        with transactional_session(factory) as db:
            row = db.get(ToolModel, {"tool_id": "file_read", "version": "1.0.0"})
            assert row is not None
            assert row.governance_enabled is False, "the fixture is operationally disabled"
            assert row.risk_level == ToolRiskLevel.CRITICAL

    def test_replacing_a_version_rewrites_its_projections(self) -> None:
        """A stale projection must not survive as a description of a replaced row."""
        factory = _factory()
        repo = SqlToolRepository(factory)
        disabled_critical = _tool("file_read", "1.0.0")
        repo.save(disabled_critical)

        enabled_low = disabled_critical.model_copy(deep=True)
        enabled_low.metadata.operational.enabled = True
        enabled_low.metadata.governance.risk_level = ToolRiskLevel.LOW
        repo.save(enabled_low)

        with transactional_session(factory) as db:
            row = db.get(ToolModel, {"tool_id": "file_read", "version": "1.0.0"})
            assert row is not None
            assert row.governance_enabled is True
            assert row.risk_level == ToolRiskLevel.LOW
        assert repo.get("file_read", "1.0.0") == enabled_low

    def test_the_payload_alone_reconstructs_the_domain_object(self) -> None:
        """The projections are not authoritative: corrupting them changes nothing returned.

        This is the invariant that keeps one fact from having three independently mutable
        representations. If reconstruction ever consulted a projection column, this fails.
        """
        factory = _factory()
        repo = SqlToolRepository(factory)
        tool = _tool("file_read", "1.0.0")
        repo.save(tool)

        with transactional_session(factory) as db:
            row = db.get(ToolModel, {"tool_id": "file_read", "version": "1.0.0"})
            assert row is not None
            row.governance_enabled = True
            row.risk_level = "LOW"

        assert repo.get("file_read", "1.0.0") == tool


class TestDurableFamilyReferentialIntegrity:
    """``tool_id`` must identify a registered family, enforced by the database."""

    def test_a_session_event_may_name_an_unregistered_family(self) -> None:
        """Session events are outside this guarantee (ADR-034 §7).

        This test once asserted the opposite, through a family foreign key on
        ``session_events``. A session event records the family a request named, and the
        denial of a request for a nonexistent tool is evidence, so migration 0007 removed
        that reference. Registered-family integrity still holds for ``tools``.
        """
        factory = _factory()
        from datetime import datetime, timezone

        from app.repositories.sql.models.agent import AgentModel
        from app.repositories.sql.models.session import SessionModel

        now = datetime.now(timezone.utc)
        with transactional_session(factory) as db:
            db.add(
                AgentModel(
                    agent_id="agent-1",
                    name="agent-1",
                    owner="secops@enterprise.internal",
                    risk_tier="LOW",
                    approved_tools=[],
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                SessionModel(
                    session_id="sess-1",
                    agent_id="agent-1",
                    created_at=now,
                    updated_at=now,
                )
            )

        with transactional_session(factory) as db:
            db.add(
                SessionEventModel(
                    event_id="evt-1",
                    session_id="sess-1",
                    agent_id="agent-1",
                    tool_id="never-registered",
                    sequence_number=1,
                    agent_sequence=1,
                    decision="DENY",
                    final_decision=None,
                    timestamp=now,
                    created_at=now,
                )
            )

        with transactional_session(factory) as db:
            stored = db.get(SessionEventModel, "evt-1")
            assert stored is not None
            assert stored.tool_id == "never-registered"

    def test_tools_is_keyed_by_family_and_version(self) -> None:
        engine = create_sql_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        inspector = inspect(engine)

        pk = inspector.get_pk_constraint("tools")
        assert pk["constrained_columns"] == ["tool_id", "version"]

        columns = {c["name"] for c in inspector.get_columns("tools")}
        assert "is_active" not in columns, (
            "family-level activation was dropped: enablement is version-level"
        )
        assert "governance_enabled" in columns

        tool_fks = inspector.get_foreign_keys("tools")
        assert any(fk["referred_table"] == "tool_families" for fk in tool_fks)

    def test_the_family_table_carries_no_version_or_governance_state(self) -> None:
        """No current_version, no family risk, no family activation."""
        engine = create_sql_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        columns = {c["name"] for c in inspect(engine).get_columns("tool_families")}

        assert columns == {"tool_id", "created_at"}
