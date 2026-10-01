"""0005_audit_identity_integrity

Align ``audit_events`` with the identity the domain has recorded since Slice 1a.

``AuditEvent`` records tool identity as three separate facts. The table held one, and held
it wrongly:

    requested_tool_id   required in the domain, absent from the table
    tool_version        nullable in the domain, absent from the table
    tool_id             nullable in the domain, NOT NULL in the table
    principal           in the table, with no domain field and no producer

The ``tool_id NOT NULL`` mismatch was the consequential one. The pipeline's
"refused at a trust boundary, before any tool resolution" path emits an event with
``tool_id`` and ``tool_version`` both unset, and ADR-030 requires the runtime to fail closed
when an audit event cannot be persisted — so the schema could not store the most
security-relevant record, and storing it would have denied the request. The invariant this
restores: **a request can be denied at the trust boundary and its denial evidence still
durably recorded, without requiring the requested tool to exist.**

No foreign key to ``tool_families`` or ``tools`` is added, deliberately. This table is
historical evidence, not a referential-integrity participant in the runtime control plane.
Because a failed audit write denies the request, any write-time constraint depending on
another table's state becomes a denial path — a missing registry row, from write ordering,
an unregistration between resolution and the audit write, or replication lag, would deny an
unrelated request. ``ON DELETE RESTRICT`` would invert the dependency further, letting
retained evidence block tool-family deletion.

The one constraint added expresses **intra-record validity only**, mirroring the domain
validator: a concrete version cannot resolve without the family it belongs to. Detecting an
audit row that names an unregistered identity belongs to a reconciliation query, not a
constraint — a dangling reference is evidence about the past, not corruption.

``principal`` is dropped as schema residue. It has no domain field, no API exposure and no
producer; retaining it would assert semantics nothing defines, and adding it to the domain
because the database happens to contain the column would reverse the authority direction.
If operator attribution is needed later it arrives as an explicit contract decision.

As in 0003 and 0004, the migration refuses to run against a populated table rather than
invent identity. ``requested_tool_id`` is NOT NULL and there is no honest source for an
existing row: ``tool_id`` and ``requested_tool_id`` are different facts, so copying one into
the other would assert that the request named what the pipeline resolved. There is no SQL
audit repository today, so no production rows exist.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-02 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERSION_CHECK = "chk_audit_events_version_requires_family"


def _refuse_if_populated(direction: str) -> None:
    """Fail closed rather than fabricate request identity for an existing row."""
    bind = op.get_bind()
    if "audit_events" not in set(sa.inspect(bind).get_table_names()):
        return

    count = bind.execute(sa.text("SELECT COUNT(*) FROM audit_events")).scalar() or 0
    if count:
        raise RuntimeError(
            f"migration 0005 ({direction}) refuses to run: 'audit_events' holds {count} "
            "row(s) and 'requested_tool_id' has no honest source for them. The requested "
            "and resolved tool identities are different facts, so copying 'tool_id' into "
            "'requested_tool_id' would assert that the request named what the pipeline "
            "resolved. Resolve the data explicitly before migrating."
        )


def upgrade() -> None:
    _refuse_if_populated("upgrade")

    op.drop_table("audit_events")
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("requested_tool_id", sa.String(length=128), nullable=False),
        sa.Column("tool_id", sa.String(length=128), nullable=True),
        sa.Column("tool_version", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Intra-record validity only. Never a constraint that reads another table.
        sa.CheckConstraint(
            "tool_version IS NULL OR tool_id IS NOT NULL", name=VERSION_CHECK
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index("idx_audit_events_agent", ["agent_id", "timestamp"], unique=False)
        batch_op.create_index("idx_audit_events_session", ["session_id", "timestamp"], unique=False)


def downgrade() -> None:
    _refuse_if_populated("downgrade")

    op.drop_table("audit_events")
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("tool_id", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("principal", sa.String(length=255), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index("idx_audit_events_agent", ["agent_id", "timestamp"], unique=False)
        batch_op.create_index("idx_audit_events_session", ["session_id", "timestamp"], unique=False)
