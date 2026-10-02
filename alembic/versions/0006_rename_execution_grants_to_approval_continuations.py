"""0006_rename_execution_grants_to_approval_continuations

Terminology only. ``execution_grants`` becomes ``approval_continuations``, and its two indexes
follow.

ADR-031 §7.1 establishes that the persisted object is **not** executable authority:
``RuntimeExecutionGrant`` is the sole executable authority type. The old name said the opposite,
and the confusion had already reached the codebase — four modules described ``ExecutionGrant`` as
the thing conferring execution authority when each meant ``RuntimeExecutionGrant``. §10 therefore
renames the model to ``ApprovalContinuation`` and this migration brings the table along.

**No schema meaning changes here.** Same columns, same types, same nullability, same primary key,
same foreign keys, same check constraints, same lifecycle. Only names move. The behavioural work
that ADR-031 §8 and §9 specify — ``resource``, a required capability binding, continuation expiry,
the epoch-aware atomic claim — is deliberately a separate change.

Two mechanics worth stating, because both differ from the migrations immediately before this one:

**This is a true rename, not a drop and recreate.** Migrations 0003 to 0005 recreated tables, which
was legitimate because a guard had established they were empty and nothing could be lost. Applying
that pattern by habit here would discard rows a rename preserves. ``approval_continuations`` holds
no production rows today, because no code writes the table, so the guard would pass trivially —
the hazard is the habit, not this table.

**Earlier migrations are left alone.** 0001 creates ``execution_grants`` and 0004 recreates it, and
both keep saying so. A historical migration describes the schema as it was; rewriting one to use
today's name would make the chain describe a past that did not happen, and would diverge from every
database already migrated through it.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-02 16:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_INDEXES = ("idx_execution_grants_agent_state", "idx_execution_grants_expiry")
_NEW_INDEXES = ("idx_approval_continuations_agent_state", "idx_approval_continuations_expiry")

# Shared column lists, so the two directions cannot drift apart.
_AGENT_STATE_COLUMNS = ["agent_id", "state"]
_EXPIRY_COLUMNS = ["expires_at", "state"]


def upgrade() -> None:
    op.rename_table("execution_grants", "approval_continuations")
    for name in _OLD_INDEXES:
        op.drop_index(name, table_name="approval_continuations")
    op.create_index(
        "idx_approval_continuations_agent_state",
        "approval_continuations",
        _AGENT_STATE_COLUMNS,
        unique=False,
    )
    op.create_index(
        "idx_approval_continuations_expiry",
        "approval_continuations",
        _EXPIRY_COLUMNS,
        unique=False,
    )


def downgrade() -> None:
    for name in _NEW_INDEXES:
        op.drop_index(name, table_name="approval_continuations")
    op.rename_table("approval_continuations", "execution_grants")
    op.create_index(
        "idx_execution_grants_agent_state",
        "execution_grants",
        _AGENT_STATE_COLUMNS,
        unique=False,
    )
    op.create_index(
        "idx_execution_grants_expiry",
        "execution_grants",
        _EXPIRY_COLUMNS,
        unique=False,
    )
