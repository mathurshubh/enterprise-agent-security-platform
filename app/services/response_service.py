from app.models.response_action import ResponseAction, ResponseType
from app.models.risk_assessment import RiskAssessment, RiskLevel


class ResponseService:
    def recommend(
        self,
        assessment: RiskAssessment,
    ) -> ResponseAction:
        response_types = {
            RiskLevel.LOW: ResponseType.MONITOR,
            RiskLevel.MEDIUM: ResponseType.ALERT,
            RiskLevel.HIGH: ResponseType.REQUIRE_APPROVAL,
            RiskLevel.CRITICAL: ResponseType.SUSPEND_AGENT,
        }

        response_type = response_types[assessment.risk_level]

        return ResponseAction(
            session_id=assessment.session_id,
            agent_id=assessment.agent_id,
            risk_level=assessment.risk_level,
            response_type=response_type,
            reason=(
                f"{assessment.risk_level.value} risk requires "
                f"{response_type.value.lower().replace('_', ' ')}"
            ),
        )
