"""SQLAlchemy persistence model for execution grants (Plane 3, ADR-030, ADR-031)."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.sql.base import Base


class ExecutionGrantModel(Base):
    """Relational representation of an authorized execution grant."""

    __tablename__ = "execution_grants"
    __table_args__ = (
        Index("idx_execution_grants_agent_state", "agent_id", "state"),
        Index("idx_execution_grants_expiry", "expires_at", "state"),
    )

    grant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
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
    execution_parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    originating_audit_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required_response: Mapped[str] = mapped_column(String(64), nullable=False)
    enforcement_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
