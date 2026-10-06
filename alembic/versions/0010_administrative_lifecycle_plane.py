"""0010_administrative_lifecycle_plane

Create the durable administrative lifecycle plane (ADR-030 L.3, ADR-024 A.6/A.8).

Three tables:

- ``agent_administrative_state`` — the authority for REGISTERED / ACTIVE / DISABLED, with
  ``administrative_version`` as its own monotonic namespace. Never compared with
  ``AgentEnforcementState.epoch`` (AP.2).
- ``agent_administrative_transitions`` — the lifecycle ledger, which is both transition
  history and authoritative lifecycle evidence (AP.6).
- ``administrative_audit_events`` — refused attempts only, with **no foreign keys**
  (ADR-034 §8): ``UNKNOWN_AGENT`` is one of the refusals it exists for, so a reference
  would make the evidence unrecordable exactly when it matters.

**The durable composition decision (F-09.D).** ``agent_administrative_state.agent_id``
references ``agents``, so the administrative row cannot be written before the identity row.
That forbids the ordering F-09.C uses in memory, where the administrative record is written
first so a failure leaves an inert orphan. Rather than inverting the ordering and accepting
a reachable orphan agent, registration commits the identity row, the administrative state
and the ledger entry in **one transaction**
(``AdministrativeStateRepository.commit_registration``).

The invariant is therefore literal rather than reachability-based:

    no durable agent exists without its administrative state

not merely "no agent is reachable without it". An orphaned row would still be a committed
agent even if every application path correctly refused it, and the existing projection has
no vocabulary for that state -- it maps an absent administrative record to ``REGISTERED``,
which is indistinguishable from a legitimately registered agent. Making the composition
atomic keeps that projection honest instead of widening it.

**No backfill.** Nothing wrote the ``agents`` table before this change, so there are no
pre-existing agents whose administrative state would need constructing. The tables are
created empty.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-07 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATES = "'REGISTERED', 'ACTIVE', 'DISABLED'"
_ACTORS = "'human', 'system', 'runtime'"


def upgrade() -> None:
    op.create_table(
        "agent_administrative_state",
        sa.Column("agent_id", sa.String(length=128), primary_key=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("administrative_version", sa.BigInteger(), nullable=False),
        sa.Column("last_transition_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.agent_id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            f"state IN ({_STATES})", name="chk_agent_administrative_state_value"
        ),
        # Registration commits version 1, so 0 is not a representable stored state.
        sa.CheckConstraint(
            "administrative_version >= 1",
            name="chk_agent_administrative_version_positive",
        ),
    )

    op.create_table(
        "agent_administrative_transitions",
        sa.Column("transition_id", sa.String(length=64), primary_key=True),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("previous_state", sa.String(length=32), nullable=True),
        sa.Column("new_state", sa.String(length=32), nullable=False),
        sa.Column("administrative_version_before", sa.BigInteger(), nullable=False),
        sa.Column("administrative_version_after", sa.BigInteger(), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.agent_id"], ondelete="RESTRICT"
        ),
        # One transition per version per agent: a duplicate would mean two records
        # claiming the same position, which is what makes the chain checkable.
        sa.UniqueConstraint(
            "agent_id",
            "administrative_version_after",
            name="uq_agent_administrative_version_after",
        ),
        sa.CheckConstraint(
            f"new_state IN ({_STATES})",
            name="chk_administrative_transition_new_state",
        ),
        sa.CheckConstraint(
            f"previous_state IS NULL OR previous_state IN ({_STATES})",
            name="chk_administrative_transition_previous_state",
        ),
        sa.CheckConstraint(
            f"actor_type IN ({_ACTORS})",
            name="chk_administrative_transition_actor_type",
        ),
        sa.CheckConstraint(
            "administrative_version_after = administrative_version_before + 1",
            name="chk_administrative_transition_version_advance",
        ),
    )
    op.create_index(
        "idx_administrative_transitions_agent_time",
        "agent_administrative_transitions",
        ["agent_id", "occurred_at"],
    )

    op.create_table(
        "administrative_audit_events",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        # A recorded identifier, not a reference. No foreign key, by design.
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("attempted_action", sa.String(length=32), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("refusal_code", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("observed_state", sa.String(length=32), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"actor_type IN ({_ACTORS})", name="chk_administrative_audit_actor_type"
        ),
        sa.CheckConstraint(
            f"observed_state IS NULL OR observed_state IN ({_STATES})",
            name="chk_administrative_audit_observed_state",
        ),
    )
    op.create_index(
        "idx_administrative_audit_agent_time",
        "administrative_audit_events",
        ["agent_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_administrative_audit_agent_time", table_name="administrative_audit_events"
    )
    op.drop_table("administrative_audit_events")
    op.drop_index(
        "idx_administrative_transitions_agent_time",
        table_name="agent_administrative_transitions",
    )
    op.drop_table("agent_administrative_transitions")
    op.drop_table("agent_administrative_state")
