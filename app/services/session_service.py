from threading import RLock

from app.models.session import Session
from app.models.session_event import SessionEvent


class SessionAlreadyExistsError(Exception):
    pass


class SessionNotFoundError(Exception):
    pass


class SessionService:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._events: list[SessionEvent] = []
        self._lock = RLock()

    def create_session(
        self,
        session: Session,
    ) -> Session:
        with self._lock:
            if session.session_id in self._sessions:
                raise SessionAlreadyExistsError()

            self._sessions[session.session_id] = session

            return session

    def get_session(
        self,
        session_id: str,
    ) -> Session:
        with self._lock:
            try:
                return self._sessions[session_id]

            except KeyError as exc:
                raise SessionNotFoundError() from exc

    def list_sessions(
        self,
    ) -> list[Session]:
        with self._lock:
            return list(self._sessions.values())

    def record_event(
        self,
        event: SessionEvent,
    ) -> SessionEvent:
        with self._lock:
            self._events.append(event)

            return event

    def list_events(
        self,
        session_id: str,
    ) -> list[SessionEvent]:
        with self._lock:
            return [
                event
                for event in self._events
                if event.session_id == session_id
            ]