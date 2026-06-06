from app.models.audit_event import (
    AuditEvent,
    Decision,
)
from app.services.audit_service import AuditService


def create_event(event_id: str = "evt-1") -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        agent_id="soc-agent",
        tool_id="file_read",
        decision=Decision.ALLOW,
    )


def test_record_event():
    service = AuditService()

    event = create_event()

    service.record_event(event)

    events = service.list_events()

    assert len(events) == 1
    assert events[0] == event


def test_list_events():
    service = AuditService()

    service.record_event(create_event("evt-1"))
    service.record_event(create_event("evt-2"))

    events = service.list_events()

    assert len(events) == 2