from uuid import UUID

from app.models.audit_event import Decision
from app.models.finding import Severity
from app.models.session_event import SessionEvent
from app.services.detection_service import (
    EXCESSIVE_DENIAL_THRESHOLD,
    DetectionService,
    session_finding_id,
)


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
    # Identity is derived from the threshold crossing, not random, so re-deriving the
    # same crossing yields the same finding (M2a).
    assert UUID(findings[0].finding_id).version == 5
    assert findings[0].finding_id == session_finding_id(
        "EXCESSIVE_DENIALS", "session-1", "agent-1", EXCESSIVE_DENIAL_THRESHOLD
    )


def test_threshold_crossing_identity_is_stable_and_scoped():
    service = DetectionService()
    denials = [create_event(Decision.DENY) for _ in range(EXCESSIVE_DENIAL_THRESHOLD)]

    first = service.detect_excessive_denials(denials)[0]
    # Re-deriving from a longer history of the same session is the same evidence.
    repeated = service.detect_excessive_denials(denials + [create_event(Decision.DENY)])[0]

    assert first.finding_id == repeated.finding_id

    other_session = service.detect_excessive_denials(
        [create_event(Decision.DENY, "session-2") for _ in range(EXCESSIVE_DENIAL_THRESHOLD)]
    )[0]
    other_agent = service.detect_excessive_denials(
        [
            create_event(Decision.DENY, "session-1", "agent-2")
            for _ in range(EXCESSIVE_DENIAL_THRESHOLD)
        ]
    )[0]

    assert len({first.finding_id, other_session.finding_id, other_agent.finding_id}) == 3


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
