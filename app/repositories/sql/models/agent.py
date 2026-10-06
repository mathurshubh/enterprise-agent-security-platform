"""SQLAlchemy persistence model for agents (Plane 3, ADR-030)."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.sql.base import Base


class AgentModel(Base):
    """Relational representation of an enterprise AI agent.

    Identity and descriptive configuration only. Administrative lifecycle state lives in
    ``agent_administrative_state`` and enforcement posture in ``agent_enforcement_state``
    (ADR-030 L.3, AP.1). There is deliberately no ``status`` column: a persisted copy of
    lifecycle state would be a cached lifecycle value on the authorization path, which
    L.7 prohibits, and would make an absent administrative record indistinguishable from
    a registered one.
    """

    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    approved_tools: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
