"""Verification tests for Alembic schema migrations and model consistency (Plane 3)."""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

import app.repositories.sql.models  # noqa: F401 - Register models
from alembic import command
from app.repositories.sql.base import Base

EXPECTED_TABLES = {
    "agents",
    "tool_families",
    "tools",
    "agent_enforcement_state",
    "agent_enforcement_transitions",
    "sessions",
    "agent_sequence_counters",
    "session_events",
    "execution_grants",
    "audit_events",
}


@pytest.fixture
def alembic_config(tmp_path: Path) -> tuple[Config, str]:
    """Provide an Alembic Config pointing to a temporary SQLite database."""
    db_path = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_path}"

    repo_root = Path(__file__).resolve().parents[3]
    ini_path = repo_root / "alembic.ini"

    config = Config(str(ini_path))
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("script_location", str(repo_root / "alembic"))
    return config, db_url


def test_alembic_upgrade_and_downgrade(alembic_config: tuple[Config, str]) -> None:
    """Verify that Alembic can apply all migrations to head and downgrade to base cleanly."""
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        # 1. Upgrade to head
        command.upgrade(config, "head")

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert EXPECTED_TABLES.issubset(tables)

        # 2. Downgrade to base
        command.downgrade(config, "base")

        inspector = inspect(engine)
        remaining_tables = set(inspector.get_table_names()) - {"alembic_version"}
        assert len(remaining_tables) == 0

    finally:
        engine.dispose()


def test_alembic_schema_matches_base_metadata(alembic_config: tuple[Config, str]) -> None:
    """Verify that the schema produced by Alembic head has zero drift from Base.metadata."""
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "head")

        with engine.connect() as conn:
            migration_ctx = MigrationContext.configure(
                conn,
                opts={"compare_type": True, "compare_server_default": True},
            )
            diff = compare_metadata(migration_ctx, Base.metadata)
            assert diff == [], f"Schema drift detected between migrations and Base.metadata: {diff}"

    finally:
        engine.dispose()


def test_0002_preserves_existing_rows_and_defaults_the_new_namespace(
    alembic_config: tuple[Config, str],
) -> None:
    """Migrating a populated database must not lose or invent a watermark.

    0002 renames the evidence watermark and adds the agent one. An existing row keeps
    its evidence position under the new name, and its agent position becomes 0 — which
    admits every recorded event into the horizon. That is the conservative direction and
    matches what those deployments already had, since the value previously compared
    against ``agent_sequence`` was a finding position always at or below the true event
    position.
    """
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0001")

        now = "2026-09-30 12:00:00+00:00"
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO agents (agent_id, name, owner, risk_tier, status,"
                    " approved_tools, created_at, updated_at) VALUES"
                    " ('agent-mig', 'Mig', 'secops', 'LOW', 'ACTIVE', '[]', :now, :now)"
                ),
                {"now": now},
            )
            conn.execute(
                text(
                    "INSERT INTO agent_enforcement_state (agent_id, epoch, current_status,"
                    " enforcement_baseline_at, enforcement_baseline_sequence, updated_at)"
                    " VALUES ('agent-mig', 4, 'ACTIVE', :now, 7, :now)"
                ),
                {"now": now},
            )

        command.upgrade(config, "0002")

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT epoch, baseline_evidence_sequence, baseline_agent_sequence"
                    " FROM agent_enforcement_state WHERE agent_id = 'agent-mig'"
                )
            ).one()

        assert row.epoch == 4, "unrelated state is carried through the rebuild"
        assert row.baseline_evidence_sequence == 7, "the evidence watermark is preserved"
        assert row.baseline_agent_sequence == 0, "the new namespace starts at 0"

        # Downgrading restores the original column and keeps the evidence position.
        command.downgrade(config, "0001")

        with engine.connect() as conn:
            legacy = conn.execute(
                text(
                    "SELECT enforcement_baseline_sequence FROM agent_enforcement_state"
                    " WHERE agent_id = 'agent-mig'"
                )
            ).scalar_one()

        assert legacy == 7

    finally:
        engine.dispose()


def test_0003_makes_concrete_tool_version_identity_durable(
    alembic_config: tuple[Config, str],
) -> None:
    """The durable model gains the two levels the domain already had.

    ``tools`` becomes keyed ``(tool_id, version)``, matching the in-memory repository and
    the identity the execution pipeline carries end to end. The family level moves to its
    own table so ``tool_id`` alone remains referable, which a refused ``SessionEvent``
    needs: it records the family it named without having resolved a version.
    """
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        # Pinned to 0003, not head: this asserts the intermediate state, in which the
        # dependents carry the family reference and no concrete one yet. 0004 adds the
        # composite references, and has its own test below.
        command.upgrade(config, "0003")
        inspector = inspect(engine)

        assert inspector.get_pk_constraint("tools")["constrained_columns"] == [
            "tool_id",
            "version",
        ]

        tool_columns = {c["name"] for c in inspector.get_columns("tools")}
        assert "governance_enabled" in tool_columns
        assert "is_active" not in tool_columns, (
            "family-level activation is dropped; enablement is version-level"
        )

        # The family carries identity and provenance only: no current_version, no family
        # risk projection, no activation flag.
        assert {c["name"] for c in inspector.get_columns("tool_families")} == {
            "tool_id",
            "created_at",
        }

        # Both dependents re-anchor to the family, because tools.tool_id is no longer unique.
        for table in ("session_events", "execution_grants"):
            referred = {fk["referred_table"] for fk in inspector.get_foreign_keys(table)}
            assert "tool_families" in referred, table
            assert "tools" not in referred, (
                f"{table} must not reference a non-unique key"
            )

    finally:
        engine.dispose()


def _seed_0002_prerequisites(engine, now: str) -> None:
    """Agent, tool and session rows the guarded tables reference."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agents (agent_id, name, owner, risk_tier, status,"
                " approved_tools, created_at, updated_at) VALUES"
                " ('agent-mig', 'Mig', 'secops', 'LOW', 'ACTIVE', '[]', :now, :now)"
            ),
            {"now": now},
        )
        conn.execute(
            text(
                "INSERT INTO sessions (session_id, agent_id, status,"
                " next_session_sequence, created_at, updated_at) VALUES"
                " ('sess-mig', 'agent-mig', 'ACTIVE', 1, :now, :now)"
            ),
            {"now": now},
        )


def _insert_legacy_tool(engine, now: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tools (tool_id, name, description, risk_level,"
                " required_permissions, metadata_payload, is_active, created_at)"
                " VALUES ('file_read', 'File Read', 'desc', 'LOW', '[]', '{}', 1, :now)"
            ),
            {"now": now},
        )


NOW = "2026-10-01 12:00:00+00:00"


def test_0003_refuses_a_populated_tools_table(
    alembic_config: tuple[Config, str],
) -> None:
    """Fail closed rather than fabricate a version for a family-level row.

    There is no deterministic ``tool_id -> version`` function once several versions exist,
    so an existing row has no honest answer. Refusing is preferable to selecting whichever
    version happens to be registered, defaulting to ``1.0.0``, or dropping the row.
    """
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0002")
        _seed_0002_prerequisites(engine, NOW)
        _insert_legacy_tool(engine, NOW)

        with pytest.raises(RuntimeError, match="refuses to run"):
            command.upgrade(config, "0003")
    finally:
        engine.dispose()


def test_0003_refuses_a_populated_execution_grants_table(
    alembic_config: tuple[Config, str],
) -> None:
    """A durable grant must name a concrete version, and an existing one names none."""
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0002")
        _seed_0002_prerequisites(engine, NOW)
        _insert_legacy_tool(engine, NOW)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO execution_grants (grant_id, session_id, agent_id,"
                    " tool_id, execution_parameters, originating_audit_event_id,"
                    " risk_score, required_response, enforcement_epoch, state,"
                    " created_at, expires_at) VALUES ('g-1', 'sess-mig', 'agent-mig',"
                    " 'file_read', '{}', 'ae-1', 10, 'ALLOW', 0, 'PENDING', :now, :now)"
                ),
                {"now": NOW},
            )

        with pytest.raises(RuntimeError, match="refuses to run"):
            command.upgrade(config, "0003")
    finally:
        engine.dispose()


def test_0004_references_the_concrete_tool_version(
    alembic_config: tuple[Config, str],
) -> None:
    """Both dependents record the version; only one keeps a family reference too.

    A composite foreign key is MATCH SIMPLE, so it is not checked when any referencing
    column is NULL. ``session_events.tool_version`` is nullable by design, so on refused
    paths the composite constraint is vacuous and the family reference is what still holds.
    ``execution_grants`` has both columns NOT NULL, so the composite subsumes it.
    """
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "head")
        inspector = inspect(engine)

        event_cols = {c["name"]: c for c in inspector.get_columns("session_events")}
        assert event_cols["tool_version"]["nullable"] is True, (
            "an event may record a refusal that never resolved an implementation"
        )
        grant_cols = {c["name"]: c for c in inspector.get_columns("execution_grants")}
        assert grant_cols["tool_version"]["nullable"] is False, (
            "a durable grant is a frozen continuation of one resolved decision"
        )

        def _refs(table: str) -> set[tuple[str, tuple[str, ...]]]:
            return {
                (fk["referred_table"], tuple(fk["constrained_columns"]))
                for fk in inspector.get_foreign_keys(table)
            }

        event_refs = _refs("session_events")
        assert ("tools", ("tool_id", "tool_version")) in event_refs
        assert ("tool_families", ("tool_id",)) in event_refs, (
            "the family reference must survive: the composite one is vacuous on NULL"
        )

        grant_refs = _refs("execution_grants")
        assert ("tools", ("tool_id", "tool_version")) in grant_refs
        assert ("tool_families", ("tool_id",)) not in grant_refs, (
            "redundant: both grant columns are NOT NULL, so the composite always applies"
        )

    finally:
        engine.dispose()


def test_0004_refuses_rows_whose_concrete_version_is_unknown(
    alembic_config: tuple[Config, str],
) -> None:
    """A legacy event has no honest version: not a value, and not NULL either.

    NULL asserts that no implementation was ever established, which for a row recorded
    before versions were persisted is not known to be true.
    """
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0003")
        _seed_0002_prerequisites(engine, NOW)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tool_families (tool_id, created_at)"
                    " VALUES ('file_read', :now)"
                ),
                {"now": NOW},
            )
            conn.execute(
                text(
                    "INSERT INTO session_events (event_id, session_id, agent_id, tool_id,"
                    " sequence_number, agent_sequence, decision, timestamp, created_at)"
                    " VALUES ('evt-1', 'sess-mig', 'agent-mig', 'file_read', 1, 1,"
                    " 'ALLOW', :now, :now)"
                ),
                {"now": NOW},
            )

        with pytest.raises(RuntimeError, match="refuses to run"):
            command.upgrade(config, "0004")
    finally:
        engine.dispose()
