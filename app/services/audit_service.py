from app.models.audit_event import AuditEvent


class AuditService:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record_event(self, event: AuditEvent) -> AuditEvent:
        self._events.append(event)
        return event

    def list_events(self) -> list[AuditEvent]:
        return self._events.copy()