"""0002_enforcement_baseline_namespaces

Separate the enforcement baseline watermark into one column per monotonic sequence
namespace.

``enforcement_baseline_sequence`` held a ``Finding.evidence_sequence`` but was also read
as a ``SessionEvent.agent_sequence`` when filtering the detection horizon. Those counters
have separate allocators and advance at different rates, so one value could not be correct
for both consumers. It is renamed to name its namespace, and the second namespace gets its
own column.

Existing rows keep their evidence watermark under the new name. The new agent-sequence
watermark defaults to 0, which admits every recorded event into the horizon — the
conservative direction, and the same behaviour those deployments already had, since the
value previously compared against ``agent_sequence`` was a finding position that was
always at or below the true event position.

Both directions rebuild the table through a batch operation with an explicit ``copy_from``.
SQLite cannot rename a column or alter a CHECK in place, and it does not reflect CHECK
constraints, so without the explicit pre-state the rebuild carries the old constraint text
forward and leaves it naming a column that no longer exists.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVIDENCE_CHECK = "chk_agent_enforcement_baseline_seq_non_negative"
AGENT_CHECK = "chk_agent_enforcement_baseline_agent_seq_non_negative"
EPOCH_CHECK = "chk_agent_enforcement_epoch_non_negative"


def _table(baseline_sequence_column: sa.Column, *extra: sa.Column) -> sa.Table:
    """Describe agent_enforcement_state as it exists before the operation being applied.

    Declared here rather than imported from the ORM so the migration keeps describing this
    revision's boundary after the models move on.
    """
    return sa.Table(
        "agent_enforcement_state",
        sa.MetaData(),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("epoch", sa.BigInteger(), nullable=False),
        sa.Column("current_status", sa.String(length=32), nullable=False),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspension_reason", sa.Text(), nullable=True),
        sa.Column("enforcement_baseline_at", sa.DateTime(timezone=True), nullable=True),
        baseline_sequence_column,
        *extra,
        sa.Column("last_transition_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("epoch >= 0", name=EPOCH_CHECK),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("agent_id"),
    )


def upgrade() -> None:
    """Upgrade schema."""
    before = _table(
        sa.Column("enforcement_baseline_sequence", sa.BigInteger(), nullable=False),
    )
    with op.batch_alter_table(
        "agent_enforcement_state", schema=None, copy_from=before
    ) as batch_op:
        batch_op.alter_column(
            "enforcement_baseline_sequence",
            new_column_name="baseline_evidence_sequence",
            existing_type=sa.BigInteger(),
            existing_nullable=False,
        )
        batch_op.add_column(
            sa.Column(
                "baseline_agent_sequence",
                sa.BigInteger(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_check_constraint(
            EVIDENCE_CHECK, "baseline_evidence_sequence >= 0"
        )
        batch_op.create_check_constraint(AGENT_CHECK, "baseline_agent_sequence >= 0")


def downgrade() -> None:
    """Downgrade schema.

    The agent-sequence watermark is dropped rather than folded back into the evidence
    watermark: they are positions in different namespaces and neither can stand for the
    other.
    """
    before = _table(
        sa.Column("baseline_evidence_sequence", sa.BigInteger(), nullable=False),
        sa.Column(
            "baseline_agent_sequence",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    with op.batch_alter_table(
        "agent_enforcement_state", schema=None, copy_from=before
    ) as batch_op:
        batch_op.drop_column("baseline_agent_sequence")
        batch_op.alter_column(
            "baseline_evidence_sequence",
            new_column_name="enforcement_baseline_sequence",
            existing_type=sa.BigInteger(),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            EVIDENCE_CHECK, "enforcement_baseline_sequence >= 0"
        )
