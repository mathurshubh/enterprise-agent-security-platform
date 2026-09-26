"""SQLAlchemy persistence model for session events (Plane 3, ADR-030)."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.sql.base import Base


class SessionEventModel(Base):
    """Relational representation of an authoritative session event in the detection horizon."""

    __tablename__ = "session_events"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_number", name="uq_session_events_session_sequence"),
        UniqueConstraint("agent_id", "agent_sequence", name="uq_session_events_agent_sequence"),
        CheckConstraint("sequence_number > 0", name="chk_session_events_seq_positive"),
        CheckConstraint("agent_sequence > 0", name="chk_session_events_agent_seq_positive"),
        # Provisional horizon indexes
        Index("idx_session_events_agent_horizon", "agent_id", "timestamp", "agent_sequence"),
        Index("idx_session_events_session_horizon", "session_id", "timestamp", "sequence_number"),
        Index("idx_session_events_timestamp_prune", "timestamp"),
    )

    event_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: f"evt-{uuid4()}",
    )
    session_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("sessions.session_id", ondelete="RESTRICT"),
        nullable=False,
    )
    agent_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("agents.agent_id", ondelete="RESTRICT"),
        nullable=False,
    )
    tool_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("tools.tool_id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    agent_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    final_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
