"""0007_session_event_evidence_independence

Remove the tool-registry foreign keys from ``session_events`` (adversarial review Finding 2,
ADR-034 §7).

0004 gave ``session_events`` two references to the tool registry: ``tool_id`` to
``tool_families`` and ``(tool_id, tool_version)`` to ``tools``. Its reasoning was sound on its
premise: a composite reference is MATCH SIMPLE and vacuous whenever ``tool_version`` is NULL, so
the family reference was kept as the only thing enforcing that a refused event "names a
registered family". 0004 is left as written; it describes the schema as it was decided.

The premise does not hold. The runtime records ``SessionEvent.tool_id`` as the family the request
*named*, before and regardless of whether that family exists, so a request for an unregistered
tool is denied by authorization and then cannot be recorded: the insert raises ``IntegrityError``
and the denial evidence is lost. That evidence is what excessive-denial detection counts, so the
constraint suppresses exactly the probing signal the session plane exists to keep.

ADR-034 established that evidence records are not referential-integrity participants in the
runtime control plane. Its §7 extends that to ``session_events``: recording a session event must
not depend on current tool-registry membership. Session and agent ownership, both sequence
uniqueness constraints, both positive-sequence checks and all indexes are unchanged.

Mechanics:

**Rows are preserved.** Unlike 0003 to 0005, nothing here is fabricated or discarded, so there is
no populated-table guard on upgrade. Every column, including ``tool_id`` and a NULL
``tool_version``, is copied exactly; no identity is canonicalized or re-resolved.

**SQLite recreates; PostgreSQL alters in place.** The references were created unnamed, which
SQLite neither names nor reflects, so on SQLite the table is rebuilt in batch mode from an
explicit definition and the rows copied across. PostgreSQL names them, so they are dropped in
place by their reflected names.

**Downgrade refuses rather than deletes.** Restoring the references would require every stored
event to name a registered family and, where a version is present, a registered version. Events
that do not are evidence, so the downgrade checks every row first and refuses before touching the
schema. It never deletes or rewrites an event to make the old constraints satisfiable.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-03 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOOL_TABLES = frozenset({"tool_families", "tools"})


def _session_events_table(*, with_tool_references: bool) -> sa.Table:
    """The full ``session_events`` definition, used as the batch copy source on SQLite."""
    items: list[sa.schema.SchemaItem] = [
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("tool_id", sa.String(length=128), nullable=False),
        sa.Column("tool_version", sa.String(length=64), nullable=True),
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
    ]
    if with_tool_references:
        items += [
            sa.ForeignKeyConstraint(["tool_id"], ["tool_families.tool_id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["tool_id", "tool_version"],
                ["tools.tool_id", "tools.version"],
                ondelete="RESTRICT",
            ),
        ]
    items += [
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("agent_id", "agent_sequence", name="uq_session_events_agent_sequence"),
        sa.UniqueConstraint("session_id", "sequence_number", name="uq_session_events_session_sequence"),
        sa.Index(
            "idx_session_events_agent_horizon", "agent_id", "timestamp", "agent_sequence"
        ),
        sa.Index(
            "idx_session_events_session_horizon", "session_id", "timestamp", "sequence_number"
        ),
        sa.Index("idx_session_events_timestamp_prune", "timestamp"),
    ]
    return sa.Table("session_events", sa.MetaData(), *items)


def _rebuild_sqlite(*, with_tool_references: bool) -> None:
    with op.batch_alter_table(
        "session_events",
        recreate="always",
        copy_from=_session_events_table(with_tool_references=with_tool_references),
    ):
        pass


def _refuse_unregistered_identities() -> None:
    """Fail closed before any schema change if a stored event would violate the old references."""
    count = op.get_bind().execute(
        sa.text(
            "SELECT COUNT(*) FROM session_events e"
            " WHERE NOT EXISTS (SELECT 1 FROM tool_families f WHERE f.tool_id = e.tool_id)"
            " OR (e.tool_version IS NOT NULL AND NOT EXISTS ("
            "     SELECT 1 FROM tools t"
            "     WHERE t.tool_id = e.tool_id AND t.version = e.tool_version))"
        )
    ).scalar() or 0
    if count:
        raise RuntimeError(
            f"migration 0007 (downgrade) refuses to run: 'session_events' holds {count} "
            "row(s) naming a tool family or version that is not registered. Restoring the "
            "tool-registry foreign keys would require deleting or rewriting that evidence. "
            "Resolve the data explicitly before downgrading."
        )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _rebuild_sqlite(with_tool_references=False)
        return

    for fk in sa.inspect(bind).get_foreign_keys("session_events"):
        if fk["referred_table"] in _TOOL_TABLES:
            op.drop_constraint(fk["name"], "session_events", type_="foreignkey")


def downgrade() -> None:
    _refuse_unregistered_identities()

    if op.get_bind().dialect.name == "sqlite":
        _rebuild_sqlite(with_tool_references=True)
        return

    op.create_foreign_key(
        None,
        "session_events",
        "tool_families",
        ["tool_id"],
        ["tool_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        None,
        "session_events",
        "tools",
        ["tool_id", "tool_version"],
        ["tool_id", "version"],
        ondelete="RESTRICT",
    )
