

from datetime import datetime, timedelta, timezone

import pytest

from app.models.audit_event import Decision
from app.models.session import Session, TerminalReason, TerminalSessionTombstone
from app.models.session_event import SessionEvent
from app.services.session_service import (
    SessionAlreadyExistsError,
    SessionBindingError,
    SessionNotFoundError,
    SessionService,
    SessionTerminalError,
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

    # The service assigns the canonical position; everything else is unchanged.
    assert result.model_dump(exclude={"sequence_number"}) == event.model_dump(
        exclude={"sequence_number"}
    )
    assert result.sequence_number == 1


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

    recorded_1 = service.record_event(event_1)
    recorded_2 = service.record_event(event_2)
    recorded_3 = service.record_event(event_3)

    events = service.list_events("session-1")

    assert len(events) == 2
    assert recorded_1 in events
    assert recorded_2 in events
    assert recorded_3 not in events


class TestSessionLifecycleAndTombstones:
    """M4-S: Session lifecycle, idle expiration, and terminal ownership tombstones."""

    def test_end_session_removes_active_session_and_records_tombstone(self) -> None:
        service = SessionService()
        service.bind_or_validate("session-1", "agent-a")
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        service.end_session("session-1", "agent-a", now_utc=t0)

        # Active session removed
        with pytest.raises(SessionNotFoundError):
            service.get_session("session-1")
        assert len(service.list_sessions()) == 0

        # Tombstone recorded
        assert service.is_terminal("session-1") is True
        tombstone = service.get_tombstone("session-1")
        assert isinstance(tombstone, TerminalSessionTombstone)
        assert tombstone.session_id == "session-1"
        assert tombstone.agent_id == "agent-a"
        assert tombstone.terminated_at == t0
        assert tombstone.terminal_reason == TerminalReason.EXPLICIT_END

    def test_end_session_is_idempotent_for_owner(self) -> None:
        service = SessionService()
        service.bind_or_validate("session-1", "agent-a")
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)

        service.end_session("session-1", "agent-a", now_utc=t0)
        # Second call by same owner is a no-op and does not update terminated_at
        service.end_session("session-1", "agent-a", now_utc=t1)

        tombstone = service.get_tombstone("session-1")
        assert tombstone.terminated_at == t0

    def test_end_session_by_non_owner_is_refused(self) -> None:
        service = SessionService()
        service.bind_or_validate("session-1", "agent-a")

        with pytest.raises(SessionBindingError) as exc_info:
            service.end_session("session-1", "agent-b")
        assert exc_info.value.owner_agent_id == "agent-a"
        assert exc_info.value.requested_agent_id == "agent-b"

        # Active session remains untouched
        assert service.get_session("session-1").agent_id == "agent-a"
        assert service.is_terminal("session-1") is False

    def test_end_session_by_non_owner_on_already_terminal_session_is_refused(self) -> None:
        service = SessionService()
        service.bind_or_validate("session-1", "agent-a")
        service.end_session("session-1", "agent-a")

        with pytest.raises(SessionBindingError) as exc_info:
            service.end_session("session-1", "agent-b")
        assert exc_info.value.owner_agent_id == "agent-a"
        assert exc_info.value.requested_agent_id == "agent-b"

    def test_end_session_on_unknown_session_raises_not_found(self) -> None:
        service = SessionService()
        with pytest.raises(SessionNotFoundError):
            service.end_session("unknown-session", "agent-a")

    def test_bind_or_validate_on_terminal_session_fails_closed(self) -> None:
        """M4-S-1: Terminal sessions cannot be rebound by any agent, including original owner."""
        service = SessionService()
        service.bind_or_validate("session-1", "agent-a")
        service.end_session("session-1", "agent-a")

        # Original owner cannot rebind
        with pytest.raises(SessionTerminalError) as exc_owner:
            service.bind_or_validate("session-1", "agent-a")
        assert exc_owner.value.owner_agent_id == "agent-a"
        assert exc_owner.value.requested_agent_id == "agent-a"
        assert isinstance(exc_owner.value, SessionBindingError)

        # Different agent cannot rebind
        with pytest.raises(SessionTerminalError) as exc_foreign:
            service.bind_or_validate("session-1", "agent-b")
        assert exc_foreign.value.owner_agent_id == "agent-a"
        assert exc_foreign.value.requested_agent_id == "agent-b"

    def test_create_session_on_terminal_session_fails_closed(self) -> None:
        service = SessionService()
        service.bind_or_validate("session-1", "agent-a")
        service.end_session("session-1", "agent-a")

        with pytest.raises(SessionTerminalError):
            service.create_session(Session(session_id="session-1", agent_id="agent-a"))

        with pytest.raises(SessionTerminalError):
            service.create_session(Session(session_id="session-1", agent_id="agent-b"))

    def test_record_event_on_terminal_session_fails_closed(self) -> None:
        service = SessionService()
        service.bind_or_validate("session-1", "agent-a")
        service.end_session("session-1", "agent-a")

        with pytest.raises(SessionTerminalError):
            service.record_event(
                SessionEvent(
                    session_id="session-1",
                    agent_id="agent-a",
                    tool_id="file_read",
                    decision=Decision.ALLOW,
                )
            )

    def test_expire_idle_sessions_requires_positive_threshold(self) -> None:
        service = SessionService()
        with pytest.raises(ValueError, match="positive"):
            service.expire_idle_sessions(0)
        with pytest.raises(ValueError, match="positive"):
            service.expire_idle_sessions(-10)

    def test_expire_idle_sessions_transitions_only_idle_sessions(self) -> None:
        service = SessionService()
        base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # session-idle: last activity at base_time
        service.bind_or_validate("session-idle", "agent-1", now_utc=base_time)

        # session-active: last activity at base_time + 40s
        t_active = base_time + timedelta(seconds=40)
        service.bind_or_validate("session-active", "agent-2", now_utc=t_active)

        # Check at base_time + 60s with threshold 30s:
        # session-idle elapsed: 60s >= 30s -> expired
        # session-active elapsed: 20s < 30s -> active
        t_check = base_time + timedelta(seconds=60)
        expired = service.expire_idle_sessions(30.0, now_utc=t_check)

        assert expired == ["session-idle"]
        assert service.is_terminal("session-idle") is True
        assert service.is_terminal("session-active") is False

        # Active session still present
        assert service.get_session("session-active").session_id == "session-active"
        # Idle session removed from active and tombstoned with IDLE_TIMEOUT
        with pytest.raises(SessionNotFoundError):
            service.get_session("session-idle")
        tombstone = service.get_tombstone("session-idle")
        assert tombstone.terminal_reason == TerminalReason.IDLE_TIMEOUT
        assert tombstone.terminated_at == t_check
        assert tombstone.agent_id == "agent-1"


class TestSessionTerminalRuntimeEnforcement:
    """End-to-end integration: terminal sessions fail closed in RuntimeService."""

    def test_runtime_execute_on_terminal_session_fails_closed(self) -> None:
        from tests.services.test_runtime_enforcement_posture import (
            AGENT_ID,
            build_runtime,
        )

        env = build_runtime()
        session_id = "test-terminal-session"

        # 1. Normal execution establishes session
        first = env.runtime.execute(
            session_id=session_id,
            agent_id=AGENT_ID,
            tool_id="file_read",
            resource="notes.txt",
        )
        assert first.event.decision == Decision.ALLOW

        # 2. Terminate the session
        env.runtime._session_service.end_session(session_id, AGENT_ID)

        # 3. Subsequent execution by owner fails closed with SESSION_BINDING_INVALID
        denied = env.runtime.execute(
            session_id=session_id,
            agent_id=AGENT_ID,
            tool_id="file_read",
            resource="notes.txt",
        )

        assert denied.event.decision == Decision.DENY
        assert denied.refusal_reason == "SESSION_BINDING_INVALID"
        assert denied.risk_assessment is None
        assert denied.enforcement_posture is None
        assert denied.response_action is None
        assert denied.authorization is None
        assert denied.findings == []