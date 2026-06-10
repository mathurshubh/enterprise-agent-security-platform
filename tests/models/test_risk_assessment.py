from datetime import timezone

from app.models.risk_assessment import RiskAssessment, RiskLevel


def test_risk_assessment_creation():
    assessment = RiskAssessment(
        session_id="session-1",
        agent_id="agent-1",
        risk_score=75,
        risk_level=RiskLevel.HIGH,
        finding_count=3,
    )

    assert assessment.session_id == "session-1"
    assert assessment.agent_id == "agent-1"
    assert assessment.risk_score == 75
    assert assessment.risk_level == RiskLevel.HIGH
    assert assessment.finding_count == 3
    assert assessment.assessed_at.tzinfo == timezone.utc
