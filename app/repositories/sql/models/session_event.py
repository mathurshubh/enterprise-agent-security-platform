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
    """Relational representation of an authoritative session event in the detection horizon.

    **Tool identity here is evidence, not a reference into the tool registry** (ADR-034 §7).
    ``tool_id`` is the family the request named, recorded literally whether or not that
    family is registered; ``tool_version`` is the implementation resolution established, or
    NULL where none was. Neither carries a foreign key to ``tool_families`` or ``tools``.

    Migration 0004 gave this table both references, on the premise that a refused event
    always names a registered family. The runtime records the requested family before and
    regardless of its existence, so that premise does not hold: a request for an
    unregistered tool would be denied and then fail to record, losing the denial that
    excessive-denial detection counts. Recording a session event must therefore not depend
    on current registry membership, and a registry deletion must not be blocked by retained
    events.

    What is enforced is the integrity of the event stream itself: session and agent
    ownership, per-session and per-agent sequence uniqueness, and positive sequences.
    """

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
    tool_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
