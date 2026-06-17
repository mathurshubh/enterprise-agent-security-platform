from app.auth.authorization_service import AuthorizationService
from app.models.runtime_result import RuntimeResult
from app.models.risk_assessment import (
    RiskAssessment,
    RiskLevel,
)
from app.models.session_event import SessionEvent
from app.services.detection_service import DetectionService
from app.services.response_service import ResponseService
from app.services.risk_service import RiskService
from app.services.session_service import SessionService


class RuntimeService:
    def __init__(
        self,
        authorization_service: AuthorizationService,
        session_service: SessionService,
        detection_service: DetectionService,
        risk_service: RiskService,
        response_service: ResponseService,
    ) -> None:
        self._authorization_service = authorization_service
        self._session_service = session_service
        self._detection_service = detection_service
        self._risk_service = risk_service
        self._response_service = response_service

    def execute(
        self,
        session_id: str,
        agent_id: str,
        tool_id: str,
        resource: str | None = None,
    ) -> RuntimeResult:
        decision = self._authorization_service.authorize(
            agent_id,
            tool_id,
            resource,
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
        if findings:
            risk_assessment = self._risk_service.assess(findings)
        else:
            risk_assessment = RiskAssessment(
                session_id=session_id,
                agent_id=agent_id,
                risk_score=0,
                risk_level=RiskLevel.LOW,
                finding_count=0,
            )

        response_action = (
            self._response_service.recommend(
                risk_assessment
            )
        )

        return RuntimeResult(
            event=recorded_event,
            findings=findings,
            risk_assessment=risk_assessment,
            response_action=response_action,
        )
