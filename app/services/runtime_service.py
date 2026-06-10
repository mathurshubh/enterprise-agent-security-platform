from app.auth.authorization_service import AuthorizationService
from app.models.runtime_result import RuntimeResult
from app.models.session_event import SessionEvent
from app.services.detection_service import DetectionService
from app.services.session_service import SessionService


class RuntimeService:
    def __init__(
        self,
        authorization_service: AuthorizationService,
        session_service: SessionService,
        detection_service: DetectionService,
    ) -> None:
        self._authorization_service = authorization_service
        self._session_service = session_service
        self._detection_service = detection_service

    def execute(
        self,
        session_id: str,
        agent_id: str,
        tool_id: str,
    ) -> RuntimeResult:
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

        recorded_event = self._session_service.record_event(event)
        session_events = self._session_service.list_events(session_id)
        findings = self._detection_service.detect_excessive_denials(
            session_events
        )

        return RuntimeResult(
            event=recorded_event,
            findings=findings,
        )
