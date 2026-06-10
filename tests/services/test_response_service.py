from app.models.response_action import ResponseType
from app.models.risk_assessment import RiskAssessment, RiskLevel
from app.services.response_service import ResponseService


def create_assessment(
    risk_level: RiskLevel,
) -> RiskAssessment:
    return RiskAssessment(
        session_id="session-1",
        agent_id="agent-1",
        risk_score=10,
        risk_level=risk_level,
        finding_count=1,
    )


def assert_response(
    risk_level: RiskLevel,
    expected_response_type: ResponseType,
    expected_reason: str,
) -> None:
    service = ResponseService()

    action = service.recommend(create_assessment(risk_level))

    assert action.session_id == "session-1"
    assert action.agent_id == "agent-1"
    assert action.risk_level == risk_level
    assert action.response_type == expected_response_type
    assert action.reason == expected_reason


def test_recommend_monitor_for_low_risk():
    assert_response(
        RiskLevel.LOW,
        ResponseType.MONITOR,
        "LOW risk requires monitor",
    )


def test_recommend_alert_for_medium_risk():
    assert_response(
        RiskLevel.MEDIUM,
        ResponseType.ALERT,
        "MEDIUM risk requires alert",
    )


def test_recommend_approval_for_high_risk():
    assert_response(
        RiskLevel.HIGH,
        ResponseType.REQUIRE_APPROVAL,
        "HIGH risk requires require approval",
    )


def test_recommend_suspension_for_critical_risk():
    assert_response(
        RiskLevel.CRITICAL,
        ResponseType.SUSPEND_AGENT,
        "CRITICAL risk requires suspend agent",
    )
