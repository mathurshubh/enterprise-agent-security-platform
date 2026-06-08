

import pytest

from app.models.session import Session
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