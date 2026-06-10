from app.auth.authorization_service import AuthorizationService
from app.models.session_event import SessionEvent
from app.services.session_service import SessionService


class RuntimeService:
    def __init__(
        self,
        authorization_service: AuthorizationService,
        session_service: SessionService,
    ) -> None:
        self._authorization_service = authorization_service
        self._session_service = session_service

    def execute(
        self,
        session_id: str,
        agent_id: str,
        tool_id: str,
    ) -> SessionEvent:
        decision = self._authorization_service.authorize(
            agent_id,
            tool_id,
        )

        event = SessionEvent(
            session_id=session_id,
            agent_id=agent_id,
            tool_id=tool_id,
            decision=decision,
        )

        return self._session_service.record_event(event)
