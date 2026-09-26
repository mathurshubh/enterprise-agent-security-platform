"""SQLAlchemy persistence models for sessions and sequence counters (Plane 3, ADR-030)."""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.sql.base import Base


class SessionModel(Base):
    """Relational representation of an agent execution session and lifecycle state."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("next_session_sequence > 0", name="chk_sessions_next_seq_positive"),
        Index("idx_sessions_agent_status", "agent_id", "status"),
    )

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("agents.agent_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    next_session_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ended_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AgentSequenceCounterModel(Base):
    """Authoritative agent-scoped monotonic sequence generator partition."""

    __tablename__ = "agent_sequence_counters"
    __table_args__ = (
        CheckConstraint("current_sequence >= 0", name="chk_agent_seq_counter_non_negative"),
    )

    agent_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("agents.agent_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    current_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
