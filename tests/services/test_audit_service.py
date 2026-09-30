import pytest
from pydantic import ValidationError

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
        requested_tool_id="file_read",
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


class TestAuditIdentityCoherence:
    """The model enforces what it has authority over, and only that.

    A resolved version without a resolved family is incoherent on its face, so the model
    refuses to hold it. Whether a resolved identity names a *registered* family is a
    repository fact the model cannot see, and asserting it here would make the model
    appear to guarantee something it has no authority to check — that belongs to the
    service and repository contracts.
    """

    @staticmethod
    def _event(**overrides) -> dict:
        base = {
            "event_id": "evt-coherence",
            "session_id": "session-1",
            "agent_id": "agent-1",
            "requested_tool_id": "file_read",
            "decision": Decision.DENY,
        }
        base.update(overrides)
        return base

    def test_a_version_without_a_family_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot resolve without"):
            AuditEvent(**self._event(tool_version="1.0.0"))

    def test_neither_resolved_field_is_required(self) -> None:
        """A trust-boundary refusal resolves nothing and must still be recordable."""
        event = AuditEvent(**self._event(requested_tool_id="never_registered"))

        assert event.tool_id is None
        assert event.tool_version is None

    def test_a_resolved_family_without_a_version_is_accepted(self) -> None:
        """Family resolved, implementation did not — a legitimate intermediate state."""
        event = AuditEvent(**self._event(tool_id="file_read"))

        assert event.tool_id == "file_read"
        assert event.tool_version is None

    def test_an_empty_requested_identity_is_recordable(self) -> None:
        """What the request carried is the point, even when it is malformed.

        An LLM emitting ``tool_id: ""`` is exactly the request worth auditing; refusing to
        record it would lose the evidence rather than validate anything.
        """
        assert AuditEvent(**self._event(requested_tool_id="")).requested_tool_id == ""

    def test_the_model_does_not_claim_the_family_is_registered(self) -> None:
        """No repository authority here, so no such assertion is made."""
        event = AuditEvent(**self._event(tool_id="not_a_real_family", tool_version="9.9.9"))

        assert event.tool_id == "not_a_real_family"
