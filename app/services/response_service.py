from app.models.response_action import ResponseAction, ResponseType
from app.models.risk_assessment import RiskAssessment, RiskLevel

RESPONSE_TYPES = {
    RiskLevel.LOW: ResponseType.MONITOR,
    RiskLevel.MEDIUM: ResponseType.ALERT,
    RiskLevel.HIGH: ResponseType.REQUIRE_APPROVAL,
    RiskLevel.CRITICAL: ResponseType.SUSPEND_AGENT,
}


class ResponseService:
    def recommend(
        self,
        assessment: RiskAssessment,
    ) -> ResponseAction:
        """Recommend a response for a session-scoped assessment."""
        return self.recommend_for_level(
            assessment.risk_level,
            session_id=assessment.session_id,
            agent_id=assessment.agent_id,
        )

    def recommend_for_level(
        self,
        risk_level: RiskLevel,
        session_id: str,
        agent_id: str,
    ) -> ResponseAction:
        """Recommend a response for a risk level, whatever scope produced it.

        M2b derives enforcement from the agent's posture rather than one session's
        assessment, so the mapping is exposed independently of the assessment object.
        """
        response_type = RESPONSE_TYPES[risk_level]

        return ResponseAction(
            session_id=session_id,
            agent_id=agent_id,
            risk_level=risk_level,
            response_type=response_type,
            reason=(
                f"{risk_level.value} risk requires "
                f"{response_type.value.lower().replace('_', ' ')}"
            ),
        )
