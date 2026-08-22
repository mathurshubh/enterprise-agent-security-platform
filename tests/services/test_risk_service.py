import pytest

from app.models.finding import Finding, Severity
from app.models.risk_assessment import RiskAssessment, RiskLevel
from app.services.risk_service import RiskService


def create_finding(
    severity: Severity,
    finding_id: str = "finding-1",
    session_id: str = "session-1",
    agent_id: str = "agent-1",
) -> Finding:
    return Finding(
        finding_id=finding_id,
        session_id=session_id,
        agent_id=agent_id,
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


def test_assess_session_empty_findings():
    service = RiskService()

    assessment = service.assess_session("session-1", "agent-1", [])

    assert assessment.session_id == "session-1"
    assert assessment.agent_id == "agent-1"
    assert assessment.risk_score == 0
    assert assessment.risk_level == RiskLevel.LOW
    assert assessment.finding_count == 0


def test_assess_session_mismatched_session_raises():
    service = RiskService()
    finding = create_finding(Severity.HIGH, session_id="session-2", agent_id="agent-1")

    with pytest.raises(
        ValueError,
        match="All findings must belong to the requested session and agent",
    ):
        service.assess_session("session-1", "agent-1", [finding])


def test_assess_session_mismatched_agent_raises():
    service = RiskService()
    finding = create_finding(Severity.HIGH, session_id="session-1", agent_id="agent-2")

    with pytest.raises(
        ValueError,
        match="All findings must belong to the requested session and agent",
    ):
        service.assess_session("session-1", "agent-1", [finding])


def test_boundary_score_thresholds():
    service = RiskService()

    # 20 (LOW + LOW) -> LOW
    a20 = service.assess([create_finding(Severity.LOW, "f1"), create_finding(Severity.LOW, "f2")])
    assert a20.risk_score == 20
    assert a20.risk_level == RiskLevel.LOW

    # 25 (MEDIUM) -> MEDIUM
    a25 = service.assess([create_finding(Severity.MEDIUM, "f1")])
    assert a25.risk_score == 25
    assert a25.risk_level == RiskLevel.MEDIUM

    # 45 (LOW + MEDIUM + LOW) -> MEDIUM
    a45 = service.assess([create_finding(Severity.LOW, "f1"), create_finding(Severity.MEDIUM, "f2"), create_finding(Severity.LOW, "f3")])
    assert a45.risk_score == 45
    assert a45.risk_level == RiskLevel.MEDIUM

    # 50 (HIGH) -> HIGH
    a50 = service.assess([create_finding(Severity.HIGH, "f1")])
    assert a50.risk_score == 50
    assert a50.risk_level == RiskLevel.HIGH

    # 95 (HIGH + MEDIUM + LOW + LOW) -> HIGH
    a95 = service.assess([
        create_finding(Severity.HIGH, "f1"),
        create_finding(Severity.MEDIUM, "f2"),
        create_finding(Severity.LOW, "f3"),
        create_finding(Severity.LOW, "f4"),
    ])
    assert a95.risk_score == 95
    assert a95.risk_level == RiskLevel.HIGH

    # 100 (CRITICAL) -> CRITICAL
    a100 = service.assess([create_finding(Severity.CRITICAL, "f1")])
    assert a100.risk_score == 100
    assert a100.risk_level == RiskLevel.CRITICAL


def test_state_storage_and_retrieval():
    service = RiskService()

    service.assess_session("session-1", "agent-1", [create_finding(Severity.HIGH, "f1")])
    service.assess_session("session-2", "agent-2", [create_finding(Severity.CRITICAL, "f2", session_id="session-2", agent_id="agent-2")])

    a1 = service.get_assessment("session-1", "agent-1")
    assert a1 is not None
    assert a1.risk_level == RiskLevel.HIGH

    a2 = service.get_assessment("session-2", "agent-2")
    assert a2 is not None
    assert a2.risk_level == RiskLevel.CRITICAL

    assert service.get_assessment("nonexistent", "agent-1") is None

    # Test list_assessments filtering
    all_assessments = service.list_assessments()
    assert len(all_assessments) == 2

    critical_only = service.list_assessments(risk_level=RiskLevel.CRITICAL)
    assert len(critical_only) == 1
    assert critical_only[0].session_id == "session-2"

    agent1_only = service.list_assessments(agent_id="agent-1")
    assert len(agent1_only) == 1
    assert agent1_only[0].session_id == "session-1"

    service.clear()
    assert len(service.list_assessments()) == 0


def test_h2_cross_agent_session_id_isolation():
    """Verify H2: Assessments for the same session_id across different agents are isolated."""
    service = RiskService()

    f1 = create_finding(Severity.HIGH, "f1", session_id="sess-shared", agent_id="agent-A")
    f2 = create_finding(Severity.LOW, "f2", session_id="sess-shared", agent_id="agent-B")

    service.assess_session("sess-shared", "agent-A", [f1])
    service.assess_session("sess-shared", "agent-B", [f2])

    a_agent_a = service.get_assessment("sess-shared", "agent-A")
    a_agent_b = service.get_assessment("sess-shared", "agent-B")

    assert a_agent_a is not None
    assert a_agent_a.agent_id == "agent-A"
    assert a_agent_a.risk_level == RiskLevel.HIGH
    assert a_agent_a.risk_score == 50

    assert a_agent_b is not None
    assert a_agent_b.agent_id == "agent-B"
    assert a_agent_b.risk_level == RiskLevel.LOW
    assert a_agent_b.risk_score == 10


def test_h2_unscoped_get_assessment_ambiguity_raises():
    """Verify unscoped get_assessment raises AmbiguousAssessmentScopeError when multiple agents match."""
    from app.services.risk_service import AmbiguousAssessmentScopeError
    service = RiskService()

    f1 = create_finding(Severity.HIGH, "f1", session_id="sess-shared", agent_id="agent-A")
    f2 = create_finding(Severity.LOW, "f2", session_id="sess-shared", agent_id="agent-B")

    service.assess_session("sess-shared", "agent-A", [f1])
    service.assess_session("sess-shared", "agent-B", [f2])

    with pytest.raises(AmbiguousAssessmentScopeError, match="agent_id is required"):
        service.get_assessment("sess-shared")
