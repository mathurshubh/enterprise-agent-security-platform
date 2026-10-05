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
    "approval_continuations",
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
        # Pinned to 0004, not head: 0006 renames ``execution_grants``, and this test asserts
        # the state at the revision that introduced the concrete-version references.
        command.upgrade(config, "0004")
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


def test_0005_aligns_audit_identity_without_control_plane_coupling(
    alembic_config: tuple[Config, str],
) -> None:
    """Three identity facts, the intra-record check, and no registry references.

    ``tool_id`` becomes nullable so the boundary-refusal record is storable: the pipeline
    emits it with no resolved identity, and ADR-030 makes a failed audit write deny the
    request, so a schema that rejected it would deny requests for naming an unknown tool.
    """
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "head")
        inspector = inspect(engine)

        columns = {c["name"]: c for c in inspector.get_columns("audit_events")}
        assert columns["requested_tool_id"]["nullable"] is False
        assert columns["tool_id"]["nullable"] is True, (
            "a request refused before resolution has no resolved family"
        )
        assert columns["tool_version"]["nullable"] is True
        assert "principal" not in columns, "schema residue with no domain field"

        assert inspector.get_foreign_keys("audit_events") == [], (
            "audit is historical evidence, not a referential-integrity participant"
        )

        check_names = {c["name"] for c in inspector.get_check_constraints("audit_events")}
        assert "chk_audit_events_version_requires_family" in check_names

    finally:
        engine.dispose()


def test_0005_refuses_to_invent_a_requested_identity(
    alembic_config: tuple[Config, str],
) -> None:
    """``tool_id`` and ``requested_tool_id`` are different facts, so neither can supply the other."""
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0004")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_events (event_id, session_id, agent_id, tool_id,"
                    " decision, timestamp, created_at) VALUES ('ae-1', 'sess-mig',"
                    " 'agent-mig', 'file_read', 'ALLOW', :now, :now)"
                ),
                {"now": NOW},
            )

        with pytest.raises(RuntimeError, match="refuses to run"):
            command.upgrade(config, "0005")
    finally:
        engine.dispose()


def test_0006_renames_the_table_without_changing_its_schema(
    alembic_config: tuple[Config, str],
) -> None:
    """Terminology only: the same columns and constraints under the new name.

    ADR-031 §7.1 establishes that the persisted object is not executable authority, so the old
    name said the opposite of what it was. §10 renames it; this asserts that nothing else moved.
    """
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0005")
        before = inspect(engine)
        old_columns = {c["name"]: (str(c["type"]), c["nullable"]) for c in before.get_columns("execution_grants")}
        old_pk = before.get_pk_constraint("execution_grants")["constrained_columns"]
        old_fks = {
            (fk["referred_table"], tuple(fk["constrained_columns"]))
            for fk in before.get_foreign_keys("execution_grants")
        }
        assert old_columns, "precondition: the table exists before the rename"

        command.upgrade(config, "0006")
        after = inspect(engine)

        assert "execution_grants" not in after.get_table_names()
        assert "approval_continuations" in after.get_table_names()

        new_columns = {
            c["name"]: (str(c["type"]), c["nullable"])
            for c in after.get_columns("approval_continuations")
        }
        assert new_columns == old_columns, "the rename must not alter columns, types or nullability"
        assert after.get_pk_constraint("approval_continuations")["constrained_columns"] == old_pk
        assert {
            (fk["referred_table"], tuple(fk["constrained_columns"]))
            for fk in after.get_foreign_keys("approval_continuations")
        } == old_fks, "foreign keys must survive the rename"

        assert {i["name"] for i in after.get_indexes("approval_continuations")} == {
            "idx_approval_continuations_agent_state",
            "idx_approval_continuations_expiry",
        }

    finally:
        engine.dispose()


def test_0006_preserves_rows_through_a_true_rename(
    alembic_config: tuple[Config, str],
) -> None:
    """A rename carries rows; a drop-and-recreate would not.

    Migrations 0003 to 0005 recreated tables, which was legitimate only because a guard had
    established they were empty. Reusing that pattern here by habit would silently discard data.
    """
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0005")
        _seed_0002_prerequisites(engine, NOW)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tool_families (tool_id, created_at) VALUES ('file_read', :now)"
                ),
                {"now": NOW},
            )
            conn.execute(
                text(
                    "INSERT INTO tools (tool_id, version, governance_enabled, risk_level,"
                    " metadata_payload, created_at) VALUES ('file_read', '1.0.0', 1, 'LOW',"
                    " '{}', :now)"
                ),
                {"now": NOW},
            )
            conn.execute(
                text(
                    "INSERT INTO execution_grants (grant_id, session_id, agent_id, tool_id,"
                    " tool_version, execution_parameters, originating_audit_event_id, risk_score,"
                    " required_response, enforcement_epoch, state, created_at, expires_at)"
                    " VALUES ('g-rename', 'sess-mig', 'agent-mig', 'file_read', '1.0.0', '{}',"
                    " 'ae-1', 75, 'REQUIRE_APPROVAL', 0, 'APPROVED', :now, :now)"
                ),
                {"now": NOW},
            )

        command.upgrade(config, "0006")

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT grant_id, state, risk_score FROM approval_continuations"
                    " WHERE grant_id = 'g-rename'"
                )
            ).one()
        assert (row.grant_id, row.state, row.risk_score) == ("g-rename", "APPROVED", 75)

        # And the rename reverses without losing the row either.
        command.downgrade(config, "0005")
        with engine.connect() as conn:
            back = conn.execute(
                text("SELECT grant_id FROM execution_grants WHERE grant_id = 'g-rename'")
            ).one()
        assert back.grant_id == "g-rename"

    finally:
        engine.dispose()


_EVENT_COLUMNS = (
    "event_id, session_id, agent_id, tool_id, tool_version, sequence_number,"
    " agent_sequence, decision, final_decision, timestamp, created_at"
)


def _seed_registered_tool(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tool_families (tool_id, created_at) VALUES ('file_read', :now)"),
            {"now": NOW},
        )
        conn.execute(
            text(
                "INSERT INTO tools (tool_id, version, governance_enabled, risk_level,"
                " metadata_payload, created_at) VALUES ('file_read', '1.0.0', 1, 'LOW',"
                " '{}', :now)"
            ),
            {"now": NOW},
        )


def _insert_event(engine, event_id: str, seq: int, tool_id: str, tool_version) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO session_events ({_EVENT_COLUMNS}) VALUES (:event_id, 'sess-mig',"
                " 'agent-mig', :tool_id, :tool_version, :seq, :seq, 'DENY', NULL, :now, :now)"
            ),
            {
                "event_id": event_id,
                "tool_id": tool_id,
                "tool_version": tool_version,
                "seq": seq,
                "now": NOW,
            },
        )


def _event_rows(engine) -> list[tuple]:
    with engine.connect() as conn:
        return [
            tuple(row)
            for row in conn.execute(
                text(f"SELECT {_EVENT_COLUMNS} FROM session_events ORDER BY event_id")
            )
        ]


def _event_refs(engine) -> set[tuple[str, tuple[str, ...]]]:
    return {
        (fk["referred_table"], tuple(fk["constrained_columns"]))
        for fk in inspect(engine).get_foreign_keys("session_events")
    }


def test_0007_removes_only_the_tool_registry_references(
    alembic_config: tuple[Config, str],
) -> None:
    """Session events are evidence (ADR-034 §7); the event stream's own integrity stays."""
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0007")
        inspector = inspect(engine)

        assert _event_refs(engine) == {
            ("sessions", ("session_id",)),
            ("agents", ("agent_id",)),
        }
        uniques = {u["name"] for u in inspector.get_unique_constraints("session_events")}
        assert {"uq_session_events_session_sequence", "uq_session_events_agent_sequence"} <= uniques
        checks = {c["name"] for c in inspector.get_check_constraints("session_events")}
        assert {"chk_session_events_seq_positive", "chk_session_events_agent_seq_positive"} <= checks
        indexes = {i["name"] for i in inspector.get_indexes("session_events")}
        assert {
            "idx_session_events_agent_horizon",
            "idx_session_events_session_horizon",
            "idx_session_events_timestamp_prune",
        } <= indexes
        for fk in inspector.get_foreign_keys("session_events"):
            assert (fk.get("options") or {}).get("ondelete") in (None, "RESTRICT"), (
                "no cascade may be introduced"
            )

    finally:
        engine.dispose()


def test_0007_preserves_existing_rows_exactly(alembic_config: tuple[Config, str]) -> None:
    """Removing a constraint fabricates nothing, so every row survives unchanged.

    A NULL ``tool_version`` is a recorded fact and must stay NULL.
    """
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0006")
        _seed_0002_prerequisites(engine, NOW)
        _seed_registered_tool(engine)
        _insert_event(engine, "evt-a", 1, "file_read", "1.0.0")
        _insert_event(engine, "evt-b", 2, "file_read", None)
        before = _event_rows(engine)

        command.upgrade(config, "0007")

        assert _event_rows(engine) == before
        assert [row[4] for row in before] == ["1.0.0", None]

    finally:
        engine.dispose()


def test_0007_downgrade_refuses_before_touching_the_schema_when_evidence_is_unregistered(
    alembic_config: tuple[Config, str],
) -> None:
    """Restoring the references would require deleting evidence, so the downgrade refuses."""
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0007")
        _seed_0002_prerequisites(engine, NOW)
        _seed_registered_tool(engine)
        _insert_event(engine, "evt-registered", 1, "file_read", "1.0.0")
        _insert_event(engine, "evt-unknown-family", 2, "never-registered", None)
        _insert_event(engine, "evt-unknown-version", 3, "file_read", "9.9.9")
        before = _event_rows(engine)

        with pytest.raises(RuntimeError, match="0007 \\(downgrade\\) refuses"):
            command.downgrade(config, "0006")

        assert _event_rows(engine) == before, "no evidence may be deleted or rewritten"
        assert ("tool_families", ("tool_id",)) not in _event_refs(engine)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0007"

    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "event_id, tool_id, tool_version",
    [("evt-unknown-family", "never-registered", None), ("evt-unknown-version", "file_read", "9.9.9")],
)
def test_0007_downgrade_refuses_each_kind_of_unregistered_identity(
    alembic_config: tuple[Config, str], event_id: str, tool_id: str, tool_version
) -> None:
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0007")
        _seed_0002_prerequisites(engine, NOW)
        _seed_registered_tool(engine)
        _insert_event(engine, event_id, 1, tool_id, tool_version)

        with pytest.raises(RuntimeError, match="0007 \\(downgrade\\) refuses"):
            command.downgrade(config, "0006")

    finally:
        engine.dispose()


def test_0007_downgrade_restores_the_references_and_keeps_rows_when_all_are_registered(
    alembic_config: tuple[Config, str],
) -> None:
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0007")
        _seed_0002_prerequisites(engine, NOW)
        _seed_registered_tool(engine)
        _insert_event(engine, "evt-a", 1, "file_read", "1.0.0")
        _insert_event(engine, "evt-b", 2, "file_read", None)
        before = _event_rows(engine)

        command.downgrade(config, "0006")

        assert _event_rows(engine) == before
        refs = _event_refs(engine)
        assert ("tool_families", ("tool_id",)) in refs
        assert ("tools", ("tool_id", "tool_version")) in refs

    finally:
        engine.dispose()


def _seed_agent_at_0007(conn, agent_id: str, *, epoch: int, now: str) -> None:
    """Insert an agent and its enforcement state as they exist at revision 0007."""
    conn.execute(
        text(
            "INSERT INTO agents (agent_id, name, owner, risk_tier, status,"
            " approved_tools, created_at, updated_at) VALUES"
            " (:aid, :aid, 'secops', 'LOW', 'ACTIVE', '[]', :now, :now)"
        ),
        {"aid": agent_id, "now": now},
    )
    conn.execute(
        text(
            "INSERT INTO agent_enforcement_state (agent_id, epoch, current_status,"
            " enforcement_baseline_at, baseline_evidence_sequence,"
            " baseline_agent_sequence, updated_at)"
            " VALUES (:aid, :epoch, 'ACTIVE', :now, 0, 0, :now)"
        ),
        {"aid": agent_id, "epoch": epoch, "now": now},
    )


def _seed_transition(conn, agent_id: str, *, tid: str, action: str, epoch: int, now: str) -> None:
    conn.execute(
        text(
            "INSERT INTO agent_enforcement_transitions (transition_id, agent_id, epoch,"
            " action, actor, reason, previous_status, new_status, occurred_at) VALUES"
            " (:tid, :aid, :epoch, :action, 'sec-ops', 'test', 'ACTIVE', 'ACTIVE', :now)"
        ),
        {"tid": tid, "aid": agent_id, "epoch": epoch, "action": action, "now": now},
    )


def test_0008_initializes_the_generation_from_the_recorded_reinstatements(
    alembic_config: tuple[Config, str],
) -> None:
    """The allocator must start where the superseded derivation left off.

    0008 replaces a timestamp-parameterised count of ``REINSTATE`` ledger entries with a
    durable column, so an existing row must be initialized to exactly that count — the one
    value for which the new mechanism agrees with the old one at the moment of cutover.

    Three agents cover the ways this can go wrong, and the three expected values are
    pairwise distinct from each other and from both ``epoch`` and zero, so no single
    mistaken source reproduces them:

    - ``agent-two-recoveries`` has 4 transitions of which 2 are ``REINSTATE``. Initializing
      from ``epoch`` would give 4; the correct answer is 2.
    - ``agent-contained`` has 1 transition and no ``REINSTATE``. An agent suspended and
      never recovered has never had a recovery generation allocated, so it must be 0 even
      though its epoch is 1.
    - ``agent-one-recovery`` distinguishes 1 from both 0 and 2.
    """
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0007")

        now = "2026-10-05 12:00:00+00:00"
        with engine.begin() as conn:
            # Suspend, reinstate, suspend, reinstate -> epoch 4, 2 recoveries.
            _seed_agent_at_0007(conn, "agent-two-recoveries", epoch=4, now=now)
            for i, action in enumerate(["SUSPEND", "REINSTATE", "SUSPEND", "REINSTATE"], 1):
                _seed_transition(
                    conn, "agent-two-recoveries", tid=f"t2-{i}", action=action, epoch=i, now=now
                )

            # Suspended, never recovered -> epoch 1, 0 recoveries.
            _seed_agent_at_0007(conn, "agent-contained", epoch=1, now=now)
            _seed_transition(
                conn, "agent-contained", tid="tc-1", action="SUSPEND", epoch=1, now=now
            )

            # One full cycle -> epoch 2, 1 recovery.
            _seed_agent_at_0007(conn, "agent-one-recovery", epoch=2, now=now)
            for i, action in enumerate(["SUSPEND", "REINSTATE"], 1):
                _seed_transition(
                    conn, "agent-one-recovery", tid=f"t1-{i}", action=action, epoch=i, now=now
                )

        command.upgrade(config, "0008")

        with engine.connect() as conn:
            rows = dict(
                conn.execute(
                    text(
                        "SELECT agent_id, recovery_generation FROM agent_enforcement_state"
                    )
                ).all()
            )
            epochs = dict(
                conn.execute(
                    text("SELECT agent_id, epoch FROM agent_enforcement_state")
                ).all()
            )

        assert rows["agent-two-recoveries"] == 2, "counts REINSTATE, not every transition"
        assert rows["agent-contained"] == 0, "no recovery means no generation allocated"
        assert rows["agent-one-recovery"] == 1

        # The epochs are carried through untouched, and differ from the generations --
        # which is what makes the assertions above discriminating.
        assert epochs == {
            "agent-two-recoveries": 4,
            "agent-contained": 1,
            "agent-one-recovery": 2,
        }

        # Downgrading drops the column and leaves every row in place.
        command.downgrade(config, "0007")

        with engine.connect() as conn:
            assert "recovery_generation" not in {
                c["name"]
                for c in inspect(engine).get_columns("agent_enforcement_state")
            }
            surviving = conn.execute(
                text("SELECT COUNT(*) FROM agent_enforcement_state")
            ).scalar_one()

        assert surviving == 3, "a rename-free column drop must not lose rows"

    finally:
        engine.dispose()


def test_0008_refuses_when_the_ledger_disagrees_with_the_epoch(
    alembic_config: tuple[Config, str],
) -> None:
    """Initializing from a ledger that contradicts the state would invent a position.

    Every ``REINSTATE`` is also an enforcement transition and ``epoch`` counts every
    committed transition, so the reinstatement count can never legitimately exceed it. A
    database where it does has lost agreement between the ledger and the state it would
    seed, and seeding the allocator anyway would place it at a position no recorded history
    supports — which L.6 then treats as authoritative for every Finding stamped afterwards.

    Refusing is the fail-closed direction: the migration is re-runnable once the
    inconsistency is resolved, whereas a silently wrong allocator start is not detectable
    afterwards.
    """
    config, db_url = alembic_config
    engine = create_engine(db_url)

    try:
        command.upgrade(config, "0007")

        now = "2026-10-05 12:00:00+00:00"
        with engine.begin() as conn:
            # epoch 1, but two recorded reinstatements -- impossible history.
            _seed_agent_at_0007(conn, "agent-inconsistent", epoch=1, now=now)
            for i in (1, 2):
                _seed_transition(
                    conn, "agent-inconsistent", tid=f"ti-{i}", action="REINSTATE", epoch=i, now=now
                )

        with pytest.raises(RuntimeError, match="recovery_generation exceeds epoch"):
            command.upgrade(config, "0008")

    finally:
        engine.dispose()
