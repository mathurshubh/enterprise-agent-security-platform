"""SQLAlchemy persistence model for audit events (Plane 3, ADR-028, ADR-030)."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.sql.base import Base


class AuditEventModel(Base):
    """Relational representation of immutable forensic audit evidence."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("idx_audit_events_session", "session_id", "timestamp"),
        Index("idx_audit_events_agent", "agent_id", "timestamp"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    principal: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
