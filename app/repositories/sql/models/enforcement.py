"""SQLAlchemy persistence models for agent enforcement state and transitions (Plane 3, ADR-030)."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.sql.base import Base


class AgentEnforcementStateModel(Base):
    """Authoritative dynamic enforcement state and concurrency epoch for an agent."""

    __tablename__ = "agent_enforcement_state"
    __table_args__ = (
        CheckConstraint("epoch >= 0", name="chk_agent_enforcement_epoch_non_negative"),
        CheckConstraint(
            "enforcement_baseline_sequence >= 0",
            name="chk_agent_enforcement_baseline_seq_non_negative",
        ),
    )

    agent_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("agents.agent_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    current_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    enforcement_baseline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enforcement_baseline_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    last_transition_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class AgentEnforcementTransitionModel(Base):
    """Immutable ledger record of an agent enforcement state transition."""

    __tablename__ = "agent_enforcement_transitions"
    __table_args__ = (
        Index("idx_enforcement_transitions_agent_time", "agent_id", "occurred_at"),
    )

    transition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("agents.agent_id", ondelete="RESTRICT"),
        nullable=False,
    )
    epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    previous_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trigger_risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trigger_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger_finding_ids: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
