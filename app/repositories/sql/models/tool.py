"""SQLAlchemy persistence models for tool families and concrete tool versions (Plane 3, ADR-030)."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.sql.base import Base


class ToolFamilyModel(Base):
    """Referential anchor for a tool family.

    A family is the unit an agent is approved for (ADR-023 A', D-1); it never identifies an
    executable implementation. This table exists so that ``tool_id`` alone is a referable
    identity: a refused ``SessionEvent`` records the family it named without having
    resolved a version, and its referential integrity has to hold anyway.

    The family carries no operational or governance state. In particular it has no
    ``current_version``, no ``risk_level`` and no ``is_active``:

    - ``current_version`` would be a hidden version-selection mechanism, and concrete
      execution identity is never inferred from family identity.
    - family ``risk_level`` is a projection over registered versions
      (``ToolService.get_family_governance``); storing it would create a second source of
      truth that can drift from its own inputs.
    - ``is_active`` would add a third activation dimension alongside version-level
      ``governance_enabled``, with no established meaning when the two disagree.

    Family existence is **derived, never independently managed**: there is no
    ``create_family`` operation on ``ToolRepository``, and a family exists exactly when at
    least one concrete version of it does. ``ToolRepository.save`` is what materialises the
    anchor.
    """

    __tablename__ = "tool_families"

    tool_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class ToolModel(Base):
    """Relational representation of one concrete tool version.

    Identity is ``(tool_id, version)``. Two versions of one tool are two rows, so the
    durable model can represent what the domain already does: a family with several
    registered versions holding different operational state.

    ``metadata_payload`` is the **canonical** representation of ``ToolMetadata`` and must be
    sufficient to reconstruct the complete ``Tool`` without consulting any other column.
    ``governance_enabled`` and ``risk_level`` are queryable projections written from the
    same source in the same statement; neither is independently authoritative, so they
    cannot drift into disagreement with the object they describe. The repository contract's
    wholesale round-trip assertion is the enforcement mechanism for that.
    """

    __tablename__ = "tools"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tool_id"], ["tool_families.tool_id"], ondelete="RESTRICT"
        ),
    )

    tool_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    governance_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
