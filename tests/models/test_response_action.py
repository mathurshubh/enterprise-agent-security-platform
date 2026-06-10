from datetime import timezone

from app.models.response_action import ResponseAction, ResponseType
from app.models.risk_assessment import RiskLevel


def test_response_action_creation():
    action = ResponseAction(
        session_id="session-1",
        agent_id="agent-1",
        risk_level=RiskLevel.HIGH,
        response_type=ResponseType.REQUIRE_APPROVAL,
        reason="High-risk agent activity detected",
    )

    assert action.session_id == "session-1"
    assert action.agent_id == "agent-1"
    assert action.risk_level == RiskLevel.HIGH
    assert action.response_type == ResponseType.REQUIRE_APPROVAL
    assert action.reason == "High-risk agent activity detected"
    assert action.created_at.tzinfo == timezone.utc
