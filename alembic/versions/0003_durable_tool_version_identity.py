"""0003_durable_tool_version_identity

Make concrete tool-version identity durable.

``tools`` was keyed by ``tool_id`` alone, so two versions of one tool could not both be
persisted — while the domain and the in-memory repository have been keyed ``(tool_id,
version)`` since Slice 1a. The family level is split into its own table so that both
identities are referable:

    tool_families(tool_id)              the unit an agent is approved for
    tools(tool_id, version)             one concrete implementation

``tool_families`` deliberately carries no state. No ``current_version`` (it would be a
hidden version-selection mechanism, and concrete execution identity is never inferred from
family identity), no family ``risk_level`` (it is a projection over registered versions and
would drift from its own inputs), and no ``is_active`` — the column dropped here, which had
no writer and would otherwise add a third activation dimension alongside version-level
``governance_enabled``.

``metadata_payload`` becomes the canonical representation of ``ToolMetadata``;
``governance_enabled`` and ``risk_level`` are queryable projections of it. The discrete
``name``, ``description`` and ``required_permissions`` columns are dropped: nothing queried
them, and keeping them would leave three independently mutable representations of one fact.

Because ``tools`` gains a composite primary key, ``tools.tool_id`` is no longer a unique key,
so the existing ``session_events.tool_id`` and ``execution_grants.tool_id`` foreign keys
cannot continue to reference it. Both are re-anchored to ``tool_families`` here. That is
forced by the key change, not an expansion of scope: adding ``tool_version`` to those
tables, and the composite references that accompany it, is the next change.

Two mechanics worth stating, because both look heavier than necessary:

Tables are dropped and recreated rather than altered in batch mode. The foreign keys
created in 0001 are unnamed, and SQLite neither names nor reflects them, so there is no
name by which to drop one. 0002 solved its equivalent problem with an explicit
``copy_from`` pre-state; here the guard below has already established the tables are empty,
so a recreate is simpler and loses nothing.

The migration refuses to run against populated tables rather than inventing identity.
There is no deterministic ``tool_id -> version`` function once several versions exist, so an
existing ``tools``, ``session_events`` or ``execution_grants`` row has no honest answer. The
alternatives were all worse: selecting whichever version happens to be registered,
defaulting to ``1.0.0``, making the column temporarily nullable, or silently dropping rows.
Production holds no SQL tool, event or grant population — every production repository is
in-memory — so the guard costs nothing today and fails closed if this is ever applied to a
database that has one.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUARDED_TABLES = ("tools", "session_events", "execution_grants")


def _refuse_if_populated(direction: str) -> None:
    """Fail closed rather than fabricate tool-version identity for existing rows."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    for table in _GUARDED_TABLES:
        if table not in existing:
            continue
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
        if count:
            raise RuntimeError(
                f"migration 0003 ({direction}) refuses to run: '{table}' holds {count} "
                "row(s), and tool-version identity cannot be derived for them. There is no "
                "deterministic tool_id -> version mapping, so any backfill would fabricate "
                "execution identity. Resolve the data explicitly before migrating."
            )


def _create_execution_grants(tool_fk_target: str) -> None:
    op.create_table(
        "execution_grants",
        sa.Column("grant_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("tool_id", sa.String(length=128), nullable=False),
        sa.Column("execution_parameters", sa.JSON(), nullable=False),
        sa.Column("originating_audit_event_id", sa.String(length=64), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("required_response", sa.String(length=64), nullable=False),
        sa.Column("enforcement_epoch", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.session_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tool_id"], [tool_fk_target], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("grant_id"),
    )
    with op.batch_alter_table("execution_grants", schema=None) as batch_op:
        batch_op.create_index("idx_execution_grants_agent_state", ["agent_id", "state"], unique=False)
        batch_op.create_index("idx_execution_grants_expiry", ["expires_at", "state"], unique=False)


def _create_session_events(tool_fk_target: str) -> None:
    op.create_table(
        "session_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("tool_id", sa.String(length=128), nullable=False),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("agent_sequence", sa.BigInteger(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("final_decision", sa.String(length=32), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("agent_sequence > 0", name="chk_session_events_agent_seq_positive"),
        sa.CheckConstraint("sequence_number > 0", name="chk_session_events_seq_positive"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.session_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tool_id"], [tool_fk_target], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("agent_id", "agent_sequence", name="uq_session_events_agent_sequence"),
        sa.UniqueConstraint("session_id", "sequence_number", name="uq_session_events_session_sequence"),
    )
    with op.batch_alter_table("session_events", schema=None) as batch_op:
        batch_op.create_index(
            "idx_session_events_agent_horizon",
            ["agent_id", "timestamp", "agent_sequence"],
            unique=False,
        )
        batch_op.create_index(
            "idx_session_events_session_horizon",
            ["session_id", "timestamp", "sequence_number"],
            unique=False,
        )
        batch_op.create_index("idx_session_events_timestamp_prune", ["timestamp"], unique=False)


def upgrade() -> None:
    _refuse_if_populated("upgrade")

    # Children first: both reference the table whose key is changing.
    op.drop_table("session_events")
    op.drop_table("execution_grants")
    op.drop_table("tools")

    op.create_table(
        "tool_families",
        sa.Column("tool_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tool_id"),
    )
    op.create_table(
        "tools",
        sa.Column("tool_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("governance_enabled", sa.Boolean(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tool_id"], ["tool_families.tool_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("tool_id", "version"),
    )

    _create_execution_grants("tool_families.tool_id")
    _create_session_events("tool_families.tool_id")


def downgrade() -> None:
    _refuse_if_populated("downgrade")

    op.drop_table("session_events")
    op.drop_table("execution_grants")
    op.drop_table("tools")
    op.drop_table("tool_families")

    op.create_table(
        "tools",
        sa.Column("tool_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("required_permissions", sa.JSON(), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tool_id"),
    )

    _create_execution_grants("tools.tool_id")
    _create_session_events("tools.tool_id")
