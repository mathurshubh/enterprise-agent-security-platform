from uuid import UUID

from app.models.audit_event import Decision
from app.models.finding import Severity
from app.models.session_event import SessionEvent
from app.services.detection_service import DetectionService


def create_event(
    decision: Decision,
    session_id: str = "session-1",
    agent_id: str = "agent-1",
) -> SessionEvent:
    return SessionEvent(
        session_id=session_id,
        agent_id=agent_id,
        tool_id="file_read",
        decision=decision,
    )


def test_detect_excessive_denials():
    service = DetectionService()
    events = [
        create_event(Decision.DENY),
        create_event(Decision.DENY),
        create_event(Decision.DENY),
    ]

    findings = service.detect_excessive_denials(events)

    assert len(findings) == 1
    assert findings[0].session_id == "session-1"
    assert findings[0].agent_id == "agent-1"
    assert findings[0].rule_name == "EXCESSIVE_DENIALS"
    assert findings[0].severity == Severity.MEDIUM
    assert findings[0].description == (
        "Session contains 3 denied actions"
    )
    assert UUID(findings[0].finding_id).version == 4


def test_no_findings_below_threshold():
    service = DetectionService()
    events = [
        create_event(Decision.DENY),
        create_event(Decision.DENY),
    ]

    findings = service.detect_excessive_denials(events)

    assert not findings


def test_ignore_non_deny_events():
    service = DetectionService()
    events = [
        create_event(Decision.DENY),
        create_event(Decision.ALLOW),
        create_event(Decision.APPROVAL_REQUIRED),
        create_event(Decision.DENY),
    ]

    findings = service.detect_excessive_denials(events)

    assert not findings


def test_multiple_sessions_generate_findings():
    service = DetectionService()
    events = [
        create_event(Decision.DENY, "session-1", "agent-1"),
        create_event(Decision.DENY, "session-2", "agent-2"),
        create_event(Decision.DENY, "session-1", "agent-1"),
        create_event(Decision.DENY, "session-2", "agent-2"),
        create_event(Decision.DENY, "session-1", "agent-1"),
        create_event(Decision.DENY, "session-2", "agent-2"),
    ]

    findings = service.detect_excessive_denials(events)

    assert len(findings) == 2
    assert {finding.session_id for finding in findings} == {
        "session-1",
        "session-2",
    }
