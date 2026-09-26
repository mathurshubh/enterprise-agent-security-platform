"""0001_initial_schema

Initial migration establishing the 9 core tables, foreign keys with ON DELETE RESTRICT,
unique sequence constraints, check constraints, and provisional indexes (Plane 3, ADR-030).

Revision ID: 0001
Revises:
Create Date: 2026-09-26 16:54:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agents",
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("risk_tier", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approved_tools", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("agent_id"),
    )

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

    op.create_table(
        "agent_enforcement_state",
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("epoch", sa.BigInteger(), nullable=False),
        sa.Column("current_status", sa.String(length=32), nullable=False),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspension_reason", sa.Text(), nullable=True),
        sa.Column("enforcement_baseline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enforcement_baseline_sequence", sa.BigInteger(), nullable=False),
        sa.Column("last_transition_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "enforcement_baseline_sequence >= 0",
            name="chk_agent_enforcement_baseline_seq_non_negative",
        ),
        sa.CheckConstraint("epoch >= 0", name="chk_agent_enforcement_epoch_non_negative"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("agent_id"),
    )

    op.create_table(
        "agent_enforcement_transitions",
        sa.Column("transition_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("epoch", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=False),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("trigger_session_id", sa.String(length=128), nullable=True),
        sa.Column("trigger_risk_level", sa.String(length=32), nullable=True),
        sa.Column("trigger_risk_score", sa.Integer(), nullable=True),
        sa.Column("trigger_finding_ids", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("transition_id"),
    )
    with op.batch_alter_table("agent_enforcement_transitions", schema=None) as batch_op:
        batch_op.create_index(
            "idx_enforcement_transitions_agent_time",
            ["agent_id", "occurred_at"],
            unique=False,
        )

    op.create_table(
        "agent_sequence_counters",
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("current_sequence", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("current_sequence >= 0", name="chk_agent_seq_counter_non_negative"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("agent_id"),
    )

    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("next_session_sequence", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_reason", sa.String(length=255), nullable=True),
        sa.CheckConstraint("next_session_sequence > 0", name="chk_sessions_next_seq_positive"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.create_index("idx_sessions_agent_status", ["agent_id", "status"], unique=False)

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
        sa.ForeignKeyConstraint(["tool_id"], ["tools.tool_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("grant_id"),
    )
    with op.batch_alter_table("execution_grants", schema=None) as batch_op:
        batch_op.create_index("idx_execution_grants_agent_state", ["agent_id", "state"], unique=False)
        batch_op.create_index("idx_execution_grants_expiry", ["expires_at", "state"], unique=False)

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
        sa.ForeignKeyConstraint(["tool_id"], ["tools.tool_id"], ondelete="RESTRICT"),
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


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("session_events", schema=None) as batch_op:
        batch_op.drop_index("idx_session_events_timestamp_prune")
        batch_op.drop_index("idx_session_events_session_horizon")
        batch_op.drop_index("idx_session_events_agent_horizon")

    op.drop_table("session_events")

    with op.batch_alter_table("execution_grants", schema=None) as batch_op:
        batch_op.drop_index("idx_execution_grants_expiry")
        batch_op.drop_index("idx_execution_grants_agent_state")

    op.drop_table("execution_grants")

    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index("idx_sessions_agent_status")

    op.drop_table("sessions")
    op.drop_table("agent_sequence_counters")

    with op.batch_alter_table("agent_enforcement_transitions", schema=None) as batch_op:
        batch_op.drop_index("idx_enforcement_transitions_agent_time")

    op.drop_table("agent_enforcement_transitions")
    op.drop_table("agent_enforcement_state")
    op.drop_table("tools")

    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index("idx_audit_events_session")
        batch_op.drop_index("idx_audit_events_agent")

    op.drop_table("audit_events")
    op.drop_table("agents")
