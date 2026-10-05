"""0008_recovery_generation_allocator

Add the authoritative recovery-generation allocator to `agent_enforcement_state`.

ADR-030 amendment DR-8(c) makes `AgentEnforcementState.recovery_generation` the authoritative
durable allocation namespace for recovery generation, replacing a timestamp-parameterised
derivation over the enforcement ledger. `REINSTATE` is the sole operation that advances it, by
exactly one, in the same compare-and-set transaction that records the reinstatement.

**Initialization of existing rows.** New agents start at 0. Existing rows are initialized to the
number of recorded `REINSTATE` entries for that agent in `agent_enforcement_transitions`, which is
precisely the quantity the superseded derivation computed. This records the number of historical
reinstatements that were actually logged; it fabricates no unrecorded event.

**Integrity check.** After initialization, every row must satisfy:

```text
recovery_generation <= epoch
```

Every `REINSTATE` is also an enforcement transition, and `epoch` counts every committed transition,
so the reinstatement count can never exceed it. A row that violates this means the ledger and the
epoch disagree about the same history, and initializing from a ledger that disagrees with the state
it is initializing would silently manufacture an allocator position. The migration refuses rather
than proceeding.

Unlike migrations 0003 to 0005 this does not refuse to run against populated tables: adding this
column to existing rows has an honest answer, and that answer is what the check above validates.
Rows are preserved; nothing is dropped or recreated.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-05 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK_NAME = "chk_agent_enforcement_recovery_generation_non_negative"


def upgrade() -> None:
    with op.batch_alter_table("agent_enforcement_state", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "recovery_generation",
                sa.BigInteger(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_check_constraint(CHECK_NAME, "recovery_generation >= 0")

    # Initialize from the recorded REINSTATE ledger, per agent.
    op.execute(
        sa.text(
            """
            UPDATE agent_enforcement_state
               SET recovery_generation = (
                     SELECT COUNT(*)
                       FROM agent_enforcement_transitions t
                      WHERE t.agent_id = agent_enforcement_state.agent_id
                        AND t.action = 'REINSTATE'
                   )
            """
        )
    )

    # Integrity check: the reinstatement count cannot exceed the total transition count.
    bind = op.get_bind()
    violations = bind.execute(
        sa.text(
            "SELECT agent_id, recovery_generation, epoch"
            "  FROM agent_enforcement_state"
            " WHERE recovery_generation > epoch"
        )
    ).fetchall()
    if violations:
        detail = ", ".join(
            f"{row[0]} (recovery_generation={row[1]}, epoch={row[2]})" for row in violations[:5]
        )
        raise RuntimeError(
            "migration 0008 integrity check failed: recovery_generation exceeds epoch for "
            f"{len(violations)} agent(s): {detail}. Every REINSTATE is also an enforcement "
            "transition, so the reinstatement count cannot exceed the committed transition "
            "count. The enforcement ledger and the epoch disagree about the same history; "
            "initializing the allocator from it would manufacture a position. Resolve the "
            "inconsistency before migrating."
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_enforcement_state", schema=None) as batch_op:
        batch_op.drop_constraint(CHECK_NAME, type_="check")
        batch_op.drop_column("recovery_generation")
