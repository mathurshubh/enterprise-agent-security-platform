from app.auth.authorization_service import AuthorizationService
from app.detection.context import DetectionContext
from app.detection.engine import DetectionEngine
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
        detection_engine: DetectionEngine,
        detection_service: DetectionService,
        risk_service: RiskService,
        response_service: ResponseService,
    ) -> None:
        self._authorization_service = authorization_service
        self._session_service = session_service
        self._detection_engine = detection_engine
        self._detection_service = detection_service
        self._risk_service = risk_service
        self._response_service = response_service

    def execute(
        self,
        session_id: str,
        agent_id: str,
        tool_id: str,
        resource: str | None = None,
        user_prompt: str = "",
        model_output: str = "",
        tool_output: str = "",
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

        content_findings = self._detection_engine.evaluate(
            DetectionContext(
                session_id=session_id,
                agent_id=agent_id,
                user_prompt=user_prompt,
                model_output=model_output,
                tool_output=tool_output,
                metadata={
                    "tool_id": tool_id,
                    "resource": resource or "",
                },
            )
        )
        session_findings = self._detection_service.detect_excessive_denials(
            session_events
        )
        findings = content_findings + session_findings

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
