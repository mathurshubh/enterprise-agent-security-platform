from app.models.audit_event import Decision
from app.models.finding import Finding, Severity
from app.models.risk_assessment import (
    RiskAssessment,
    RiskLevel,
)
from app.models.runtime_result import RuntimeResult
from app.models.session_event import SessionEvent


def test_runtime_result_creation():
    event = SessionEvent(
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
        decision=Decision.DENY,
    )
    finding = Finding(
        finding_id="finding-1",
        session_id="session-1",
        agent_id="agent-1",
        rule_name="EXCESSIVE_DENIALS",
        severity=Severity.MEDIUM,
        description="Session contains 3 denied actions",
    )

    risk_assessment = RiskAssessment(
        session_id="session-1",
        agent_id="agent-1",
        risk_score=25,
        risk_level=RiskLevel.MEDIUM,
        finding_count=1,
    )

    result = RuntimeResult(
        event=event,
        findings=[finding],
        risk_assessment=risk_assessment,
    )

    assert result.event == event
    assert result.findings == [finding]
    assert result.risk_assessment == risk_assessment
