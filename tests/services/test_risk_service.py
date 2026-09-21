import pytest

from app.models.finding import Finding, Severity
from app.models.risk_assessment import RiskLevel
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


def test_reconstruction_derives_one_assessment_per_session_and_agent():
    """Replaces `test_state_storage_and_retrieval` (M4-RISK).

    That test asserted the service stored assessments and read them back. There is no
    store: the same questions are now answered by deriving from the evidence supplied.
    """
    service = RiskService()
    findings = [
        create_finding(Severity.HIGH, "f1"),
        create_finding(Severity.CRITICAL, "f2", session_id="session-2", agent_id="agent-2"),
    ]

    assessments = service.reconstruct(findings)

    assert [(a.session_id, a.risk_level) for a in assessments] == [
        ("session-1", RiskLevel.HIGH),
        ("session-2", RiskLevel.CRITICAL),
    ]


def test_reconstruction_is_ordered_by_session_id():
    """Deterministic rather than inherited from a store's insertion order."""
    service = RiskService()
    findings = [
        create_finding(Severity.LOW, "fc", session_id="session-c"),
        create_finding(Severity.LOW, "fa", session_id="session-a"),
        create_finding(Severity.LOW, "fb", session_id="session-b"),
    ]

    assessments = service.reconstruct(findings)

    assert [a.session_id for a in assessments] == ["session-a", "session-b", "session-c"]


def test_a_pair_without_evidence_yields_no_assessment():
    """Evidence-defined existence: nothing derives from nothing."""
    service = RiskService()

    assert service.reconstruct([]) == []
    assert service.reconstruct_for_session([], "session-1") is None


def test_assessed_at_comes_from_the_evidence_not_the_clock():
    """Two derivations of unchanged evidence must be identical, so a derived view can
    be compared and cached. A read-time clock would report when it was looked at."""
    service = RiskService()
    findings = [create_finding(Severity.HIGH, "f1")]

    first = service.reconstruct(findings)
    second = service.reconstruct(findings)

    assert first == second


def test_h2_cross_agent_session_id_isolation():
    """Verify H2: Assessments for the same session_id across different agents are isolated."""
    service = RiskService()

    f1 = create_finding(Severity.HIGH, "f1", session_id="sess-shared", agent_id="agent-A")
    f2 = create_finding(Severity.LOW, "f2", session_id="sess-shared", agent_id="agent-B")

    a_agent_a = service.reconstruct_for_session([f1, f2], "sess-shared", agent_id="agent-A")
    a_agent_b = service.reconstruct_for_session([f1, f2], "sess-shared", agent_id="agent-B")

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

    with pytest.raises(AmbiguousAssessmentScopeError, match="agent_id is required"):
        service.reconstruct_for_session([f1, f2], "sess-shared")
