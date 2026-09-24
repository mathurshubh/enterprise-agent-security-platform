from app.models.audit_event import (
    AuditEvent,
    Decision,
)
from tests.conftest import create_test_audit_service


def create_event(
    event_id: str = "evt-1",
    session_id: str = "session-1",
    agent_id: str = "soc-agent",
) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        session_id=session_id,
        agent_id=agent_id,
        tool_id="file_read",
        decision=Decision.ALLOW,
    )


def test_record_event():
    service = create_test_audit_service()

    event = create_event()

    returned = service.record_event(event)

    assert returned is event
    events = service.list_events()

    assert len(events) == 1
    assert events[0] == event


def test_list_events():
    service = create_test_audit_service()

    service.record_event(create_event("evt-1"))
    service.record_event(create_event("evt-2"))

    events = service.list_events()

    assert len(events) == 2


def test_get_event():
    service = create_test_audit_service()
    event = create_event("evt-lookup")
    service.record_event(event)

    found = service.get_event("evt-lookup")
    assert found is not None
    assert found.event_id == "evt-lookup"

    missing = service.get_event("evt-nonexistent")
    assert missing is None


def test_list_events_filtering():
    service = create_test_audit_service()

    service.record_event(create_event("evt-1", session_id="sess-A", agent_id="agent-1"))
    service.record_event(create_event("evt-2", session_id="sess-A", agent_id="agent-2"))
    service.record_event(create_event("evt-3", session_id="sess-B", agent_id="agent-1"))

    by_session = service.list_events(session_id="sess-A")
    assert len(by_session) == 2
    assert {e.event_id for e in by_session} == {"evt-1", "evt-2"}

    by_agent = service.list_events(agent_id="agent-1")
    assert len(by_agent) == 2
    assert {e.event_id for e in by_agent} == {"evt-1", "evt-3"}

    by_both = service.list_events(session_id="sess-A", agent_id="agent-1")
    assert len(by_both) == 1
    assert by_both[0].event_id == "evt-1"
