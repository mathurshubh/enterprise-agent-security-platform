"""0004_concrete_version_references

Carry concrete tool-version identity into the two tables that consume it.

0003 made ``tools`` keyed ``(tool_id, version)`` and left the dependents referencing the
family anchor only. They now record the version as well, and reference the concrete row:

    session_events.tool_version   NULL     family FK + composite FK
    execution_grants.tool_version NOT NULL composite FK

The asymmetry is deliberate and follows the domain. An ``ExecutionGrant`` is a frozen
continuation of one evaluated authorization decision, which resolved to one implementation,
so a durable grant always names a version and its composite reference is always checked. A
``SessionEvent`` may record a refusal that never resolved one, so its version is nullable.

That nullability is why ``session_events`` keeps two references rather than replacing the
family one. A composite foreign key is MATCH SIMPLE: it is **not checked at all** when any
referencing column is NULL. So on exactly the refused paths — the security-relevant ones —
the composite constraint is vacuous, and the family reference on ``tool_id`` alone is what
still enforces that the event names a registered family. Dropping it in favour of the
composite would have silently removed referential integrity from every refused event.

``execution_grants`` needs no family reference: both of its columns are NOT NULL, so the
composite reference subsumes it.

As in 0003, the tables are recreated rather than altered in batch mode, because the foreign
keys created there are unnamed and SQLite neither names nor reflects them; and the migration
refuses to run against populated tables rather than inventing identity.
``execution_grants.tool_version`` is NOT NULL with no honest backfill — there is no
deterministic ``tool_id -> version`` function — and a NULL for an existing ``session_events``
row would assert that no implementation was ever established, which for a legacy row is not
known to be true.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUARDED_TABLES = ("session_events", "execution_grants")


def _refuse_if_populated(direction: str) -> None:
    """Fail closed rather than fabricate — or deny — concrete tool-version identity."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    for table in _GUARDED_TABLES:
        if table not in existing:
            continue
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
        if count:
            raise RuntimeError(
                f"migration 0004 ({direction}) refuses to run: '{table}' holds {count} "
                "row(s) whose concrete tool version is unknown. There is no deterministic "
                "tool_id -> version mapping, so a backfill would fabricate execution "
                "identity, and a NULL would assert that no version was ever established. "
                "Resolve the data explicitly before migrating."
            )


def _create_execution_grants(*, with_version: bool) -> None:
    columns: list[sa.schema.SchemaItem] = [
        sa.Column("grant_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("tool_id", sa.String(length=128), nullable=False),
    ]
    if with_version:
        columns.append(sa.Column("tool_version", sa.String(length=64), nullable=False))
    columns += [
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
    ]
    if with_version:
        columns.append(
            sa.ForeignKeyConstraint(
                ["tool_id", "tool_version"],
                ["tools.tool_id", "tools.version"],
                ondelete="RESTRICT",
            )
        )
    else:
        columns.append(
            sa.ForeignKeyConstraint(
                ["tool_id"], ["tool_families.tool_id"], ondelete="RESTRICT"
            )
        )
    columns.append(sa.PrimaryKeyConstraint("grant_id"))

    op.create_table("execution_grants", *columns)
    with op.batch_alter_table("execution_grants", schema=None) as batch_op:
        batch_op.create_index("idx_execution_grants_agent_state", ["agent_id", "state"], unique=False)
        batch_op.create_index("idx_execution_grants_expiry", ["expires_at", "state"], unique=False)


def _create_session_events(*, with_version: bool) -> None:
    columns: list[sa.schema.SchemaItem] = [
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("tool_id", sa.String(length=128), nullable=False),
    ]
    if with_version:
        columns.append(sa.Column("tool_version", sa.String(length=64), nullable=True))
    columns += [
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
        # Retained in both directions: the composite reference below cannot stand in for it.
        sa.ForeignKeyConstraint(["tool_id"], ["tool_families.tool_id"], ondelete="RESTRICT"),
    ]
    if with_version:
        columns.append(
            sa.ForeignKeyConstraint(
                ["tool_id", "tool_version"],
                ["tools.tool_id", "tools.version"],
                ondelete="RESTRICT",
            )
        )
    columns += [
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("agent_id", "agent_sequence", name="uq_session_events_agent_sequence"),
        sa.UniqueConstraint("session_id", "sequence_number", name="uq_session_events_session_sequence"),
    ]

    op.create_table("session_events", *columns)
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

    op.drop_table("session_events")
    op.drop_table("execution_grants")

    _create_execution_grants(with_version=True)
    _create_session_events(with_version=True)


def downgrade() -> None:
    _refuse_if_populated("downgrade")

    op.drop_table("session_events")
    op.drop_table("execution_grants")

    _create_execution_grants(with_version=False)
    _create_session_events(with_version=False)
