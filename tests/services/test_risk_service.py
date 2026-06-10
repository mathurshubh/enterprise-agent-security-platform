import pytest

from app.models.finding import Finding, Severity
from app.models.risk_assessment import RiskLevel
from app.services.risk_service import RiskService


def create_finding(
    severity: Severity,
    finding_id: str = "finding-1",
) -> Finding:
    return Finding(
        finding_id=finding_id,
        session_id="session-1",
        agent_id="agent-1",
        rule_name="TEST_RULE",
        severity=severity,
        description="Test finding",
    )


def test_assess_low_risk():
    service = RiskService()

    assessment = service.assess([create_finding(Severity.LOW)])

    assert assessment.session_id == "session-1"
    assert assessment.agent_id == "agent-1"
    assert assessment.risk_score == 10
    assert assessment.risk_level == RiskLevel.LOW
    assert assessment.finding_count == 1


def test_assess_medium_risk():
    service = RiskService()

    assessment = service.assess([create_finding(Severity.MEDIUM)])

    assert assessment.session_id == "session-1"
    assert assessment.agent_id == "agent-1"
    assert assessment.risk_score == 25
    assert assessment.risk_level == RiskLevel.MEDIUM
    assert assessment.finding_count == 1


def test_assess_high_risk():
    service = RiskService()

    assessment = service.assess([create_finding(Severity.HIGH)])

    assert assessment.session_id == "session-1"
    assert assessment.agent_id == "agent-1"
    assert assessment.risk_score == 50
    assert assessment.risk_level == RiskLevel.HIGH
    assert assessment.finding_count == 1


def test_assess_critical_risk():
    service = RiskService()

    assessment = service.assess([create_finding(Severity.CRITICAL)])

    assert assessment.session_id == "session-1"
    assert assessment.agent_id == "agent-1"
    assert assessment.risk_score == 100
    assert assessment.risk_level == RiskLevel.CRITICAL
    assert assessment.finding_count == 1


def test_multiple_medium_findings_accumulate_risk():
    service = RiskService()
    findings = [
        create_finding(Severity.MEDIUM, "finding-1"),
        create_finding(Severity.MEDIUM, "finding-2"),
    ]

    assessment = service.assess(findings)

    assert assessment.session_id == "session-1"
    assert assessment.agent_id == "agent-1"
    assert assessment.risk_score == 50
    assert assessment.risk_level == RiskLevel.HIGH
    assert assessment.finding_count == 2


def test_mixed_severity_findings_accumulate_risk():
    service = RiskService()
    findings = [
        create_finding(Severity.MEDIUM, "finding-1"),
        create_finding(Severity.HIGH, "finding-2"),
    ]

    assessment = service.assess(findings)

    assert assessment.session_id == "session-1"
    assert assessment.agent_id == "agent-1"
    assert assessment.risk_score == 75
    assert assessment.risk_level == RiskLevel.HIGH
    assert assessment.finding_count == 2


def test_assess_empty_findings():
    service = RiskService()

    with pytest.raises(
        ValueError,
        match="At least one finding is required",
    ):
        service.assess([])
