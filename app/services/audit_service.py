from app.models.audit_event import AuditEvent
from app.repositories.interfaces.audit_evidence_repository import (
    AuditEvidenceRepository,
)


class AuditService:
    def __init__(
        self,
        audit_repository: AuditEvidenceRepository,
    ) -> None:
        self._audit_repository = audit_repository

    @property
    def audit_repository(self) -> AuditEvidenceRepository:
        """Injected AuditEvidenceRepository protocol instance."""
        return self._audit_repository

    def record_event(self, event: AuditEvent) -> AuditEvent:
        self._audit_repository.append(event)
        return event

    def list_events(
        self,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        return self._audit_repository.query(
            session_id=session_id,
            agent_id=agent_id,
            limit=limit,
            offset=offset,
        )

    def get_event(self, event_id: str) -> AuditEvent | None:
        return self._audit_repository.get(event_id)
