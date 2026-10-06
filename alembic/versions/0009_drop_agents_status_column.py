"""0009_drop_agents_status_column

Remove ``agents.status``. Administrative lifecycle state becomes authoritative in its own
plane (ADR-030 AP.1); a persisted copy on the agent record would be a cached lifecycle
value on the authorization path, which L.7 prohibits.

**No backfill, and that is a finding rather than an omission.** A reconciliation performed
before this change established that no application path writes the ``agents`` table: the
composition root wires ``InMemoryAgentRepository``, no ``SqlAgentRepository`` exists, the
repository factory is never called from ``app/``, and the only code constructing
``AgentModel`` is test setup. Every agent is created at bootstrap and does not survive the
process, so there is no durable population whose lifecycle state could need migrating into
the administrative plane.

The table itself is not empty by construction -- it is the foreign-key target for
enforcement state, session events and the sequence counters -- so this migration does not
refuse to run against rows. It drops one column from whatever is there, which is the
honest operation: for any row that exists, the column held a value no application wrote.

**Durable successor requirement (F-09.D).** When a durable ``SqlAgentRepository``
composition is introduced, durable agent creation and durable administrative-state
creation must be composed so that an agent cannot commit without its corresponding
administrative state. That is the durable analogue of the invariant that holds here today:
only two writes to the agent store exist in ``app/``, and the one that creates an agent
runs after the administrative record has committed.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-06 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_column("status")


def downgrade() -> None:
    # Restored with the model default the column previously carried. Downgrading cannot
    # recover a lifecycle value from the administrative plane and must not invent one:
    # REGISTERED is non-executable, so a downgraded deployment fails closed rather than
    # resurrecting agents into service.
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="REGISTERED",
            )
        )
