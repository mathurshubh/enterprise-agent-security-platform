from app.models.audit_event import AuditEvent
from app.repositories.interfaces.audit_evidence_repository import (
    AuditEvidenceRepository,
)


class AuditService:
    def __init__(
        self,
        audit_repository: AuditEvidenceRepository | None = None,
    ) -> None:
        self._audit_repository = audit_repository
        # In PR #180, repository is accepted as dependency wiring only.
        # Existing in-memory state remains authoritative until PR #182.
        self._events: list[AuditEvent] = []

    @property
    def audit_repository(self) -> AuditEvidenceRepository | None:
        """Injected AuditEvidenceRepository protocol instance (if supplied)."""
        return self._audit_repository

    def record_event(self, event: AuditEvent) -> AuditEvent:
        self._events.append(event)
        return event

    def list_events(self) -> list[AuditEvent]:
        return self._events.copy()
