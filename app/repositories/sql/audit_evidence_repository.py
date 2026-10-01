"""SQL implementation of AuditEvidenceRepository for immutable audit evidence (Plane 3, ADR-028, ADR-030)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.models.audit_event import AuditEvent, Decision
from app.repositories.interfaces.audit_evidence_repository import (
    AuditEvidenceRepository,
)
from app.repositories.sql.models.audit_event import AuditEventModel
from app.repositories.sql.session import transactional_session
from app.repositories.sql.session_repository import _ensure_utc


class SqlAuditEvidenceRepository(AuditEvidenceRepository):
    """SQLAlchemy implementation of AuditEvidenceRepository.

    Invariants:
    - Append-only: no update or delete operation exists, matching the interface.
    - Self-contained identity: the three tool-identity facts are stored literally and read
      back without consulting the registry, so a stored record's meaning cannot be changed
      by later registry state (the audit identity contract).
    - Recordable refusals: an event refused at a trust boundary — ``tool_id`` and
      ``tool_version`` both NULL, ``requested_tool_id`` naming something that may not
      exist — persists like any other. ADR-030 makes a failed audit write deny the request,
      so a schema that could not store this record would deny requests for naming an
      unknown tool.
    - Object Isolation: returned events are reconstructed from rows, sharing no state with
      storage or with each other.
    - Deterministic Ordering: ``query`` orders by ``(timestamp, event_id)``, matching the
      in-memory adapter, so pagination is stable across timestamp ties.
    """

    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    def append(self, event: AuditEvent) -> None:
        with transactional_session(self._session_factory) as db:
            db.add(
                AuditEventModel(
                    event_id=event.event_id,
                    session_id=event.session_id,
                    agent_id=event.agent_id,
                    requested_tool_id=event.requested_tool_id,
                    tool_id=event.tool_id,
                    tool_version=event.tool_version,
                    decision=(
                        event.decision.value
                        if hasattr(event.decision, "value")
                        else str(event.decision)
                    ),
                    timestamp=event.timestamp,
                )
            )

    def get(self, event_id: str) -> AuditEvent | None:
        with transactional_session(self._session_factory) as db:
            row = db.get(AuditEventModel, event_id)
            if row is None:
                return None
            return self._to_domain(row)

    def query(
        self,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        with transactional_session(self._session_factory) as db:
            stmt = select(AuditEventModel)
            if session_id is not None:
                stmt = stmt.where(AuditEventModel.session_id == session_id)
            if agent_id is not None:
                stmt = stmt.where(AuditEventModel.agent_id == agent_id)

            # Primary key timestamp, secondary key event_id: ties must not reorder between
            # pages, or pagination silently skips and repeats records.
            stmt = stmt.order_by(
                AuditEventModel.timestamp.asc(), AuditEventModel.event_id.asc()
            ).limit(limit).offset(offset)

            return [self._to_domain(row) for row in db.execute(stmt).scalars()]

    @staticmethod
    def _to_domain(row: AuditEventModel) -> AuditEvent:
        return AuditEvent(
            event_id=row.event_id,
            session_id=row.session_id,
            agent_id=row.agent_id,
            requested_tool_id=row.requested_tool_id,
            tool_id=row.tool_id,
            tool_version=row.tool_version,
            decision=Decision(row.decision),
            timestamp=_ensure_utc(row.timestamp),
        )
