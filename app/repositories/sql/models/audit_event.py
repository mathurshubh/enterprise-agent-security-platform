"""SQLAlchemy persistence model for audit events (Plane 3, ADR-028, ADR-030)."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.sql.base import Base


class AuditEventModel(Base):
    """Relational representation of immutable forensic audit evidence.

    **This table is historical evidence, not a referential-integrity participant in the
    runtime control plane.** It holds no foreign key to ``tool_families`` or ``tools``, and
    that is a decision rather than an omission.

    ADR-030 requires the runtime pipeline to fail closed when an audit event cannot be
    persisted, and the pipeline's ``record_event`` calls are unguarded, so a failed audit
    write denies the request. Any write-time constraint that depends on another table's
    state would therefore become a denial path: a ``tool_families`` row absent for any
    reason — write ordering, a family unregistered between resolution and the audit write,
    replication lag — would deny an unrelated request. ``ON DELETE RESTRICT`` would invert
    the dependency further still, letting retained evidence block tool-family deletion.

    So constraints here express **intra-record validity only**. The check below mirrors the
    domain validator and is satisfiable from the row alone. A check, trigger or function
    consulting ``tools`` or ``tool_families`` would turn current control-plane state into a
    prerequisite for recording history, which is what this contract exists to prevent.
    Detecting an audit row that names an unregistered identity is a reconciliation query,
    not a constraint: a dangling reference is evidence about the past, not corruption.

    Tool identity is three columns because they are three different facts:

    - ``requested_tool_id`` is what crossed the trust boundary, recorded as received and
      never validated against anything. Required. A request naming a tool that does not
      exist is the case most worth auditing, and it must be recordable.
    - ``tool_id`` is the resolved family, NULL where a request was refused at a trust
      boundary before any resolution occurred.
    - ``tool_version`` is the resolved concrete implementation, NULL where a family
      resolved but no implementation did.

    NULL is a recorded fact — "no resolution occurred" — not missing data. Interpreting any
    of the three requires no join, which is what keeps a stored record's meaning immune to
    later registry change.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("idx_audit_events_session", "session_id", "timestamp"),
        Index("idx_audit_events_agent", "agent_id", "timestamp"),
        CheckConstraint(
            "tool_version IS NULL OR tool_id IS NOT NULL",
            name="chk_audit_events_version_requires_family",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_tool_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
