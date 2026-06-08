

import pytest

from app.models.session import Session
from app.models.audit_event import Decision
from app.models.session_event import SessionEvent
from app.services.session_service import (
    SessionAlreadyExistsError,
    SessionNotFoundError,
    SessionService,
)


def create_session(
    session_id: str = "session-1",
    agent_id: str = "agent-1",
) -> Session:
    return Session(
        session_id=session_id,
        agent_id=agent_id,
    )


def test_create_session():
    service = SessionService()

    session = create_session()

    result = service.create_session(session)

    assert result == session


def test_duplicate_session_rejected():
    service = SessionService()

    session = create_session()

    service.create_session(session)

    with pytest.raises(SessionAlreadyExistsError):
        service.create_session(session)


def test_get_unknown_session():
    service = SessionService()

    with pytest.raises(SessionNotFoundError):
        service.get_session("unknown-session")


def test_list_sessions():
    service = SessionService()

    session_1 = create_session("session-1")
    session_2 = create_session("session-2")

    service.create_session(session_1)
    service.create_session(session_2)

    sessions = service.list_sessions()

    assert len(sessions) == 2
    assert session_1 in sessions
    assert session_2 in sessions


def test_record_event():
    service = SessionService()

    event = SessionEvent(
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
        decision=Decision.ALLOW,
    )

    result = service.record_event(event)

    assert result == event


def test_list_events():
    service = SessionService()

    event_1 = SessionEvent(
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
        decision=Decision.ALLOW,
    )

    event_2 = SessionEvent(
        session_id="session-1",
        agent_id="agent-1",
        tool_id="web_fetch",
        decision=Decision.DENY,
    )

    event_3 = SessionEvent(
        session_id="session-2",
        agent_id="agent-2",
        tool_id="shell_execute",
        decision=Decision.ALLOW,
    )

    service.record_event(event_1)
    service.record_event(event_2)
    service.record_event(event_3)

    events = service.list_events("session-1")

    assert len(events) == 2
    assert event_1 in events
    assert event_2 in events
    assert event_3 not in events