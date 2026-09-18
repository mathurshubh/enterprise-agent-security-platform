from threading import RLock

from app.models.session import Session
from app.models.session_event import SessionEvent


class SessionAlreadyExistsError(Exception):
    pass


class SessionNotFoundError(Exception):
    pass


class SessionBindingError(Exception):
    """Raised when a session is used by an agent that does not own it.

    A session is security-owned by exactly one agent. Evidence gathered in a session
    feeds that agent's enforcement posture (M2b), so allowing another agent to write
    into it would let one workload manipulate another workload's security state.
    """

    def __init__(self, session_id: str, owner_agent_id: str, requested_agent_id: str) -> None:
        super().__init__(
            f"Session '{session_id}' is owned by agent '{owner_agent_id}', "
            f"not '{requested_agent_id}'"
        )
        self.session_id = session_id
        self.owner_agent_id = owner_agent_id
        self.requested_agent_id = requested_agent_id


class SessionService:
    """Sessions and their ownership.

    Ownership is established once, atomically, and never changes. It is the integrity
    boundary for agent-scoped enforcement: behavioural evidence is only trustworthy if
    the agent it is attributed to is the agent that produced it.
    """

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

    def bind_or_validate(
        self,
        session_id: str,
        agent_id: str,
    ) -> Session:
        """Return the session owned by ``agent_id``, establishing ownership if new.

        Establishment and validation happen under one lock, so two concurrent first
        uses cannot produce two competing owners: exactly one establishes ownership and
        the other is measured against it.

        Ownership is permanent for the life of the session. Establishing it on first use
        is the transitional model while callers supply their own identifiers; the target
        architecture is a server-issued, unpredictable identifier, which also removes the
        ability to squat an identifier another agent intends to use.

        Raises:
            SessionBindingError: the session belongs to a different agent.
        """
        with self._lock:
            existing = self._sessions.get(session_id)

            if existing is None:
                session = Session(session_id=session_id, agent_id=agent_id)
                self._sessions[session_id] = session
                return session

            if existing.agent_id != agent_id:
                raise SessionBindingError(session_id, existing.agent_id, agent_id)

            return existing

    def record_event(
        self,
        event: SessionEvent,
    ) -> SessionEvent:
        """Record a session event, refusing one attributed against session ownership."""
        with self._lock:
            owner = self._sessions.get(event.session_id)
            if owner is not None and owner.agent_id != event.agent_id:
                raise SessionBindingError(
                    event.session_id, owner.agent_id, event.agent_id
                )

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