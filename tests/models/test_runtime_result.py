from app.models.audit_event import Decision
from app.models.execution_binding import ExecutionBinding
from app.models.finding import Finding, Severity
from app.models.response_action import (
    ResponseAction,
    ResponseType,
)
from app.models.risk_assessment import (
    RiskAssessment,
    RiskLevel,
)
from app.models.runtime_result import RuntimeResult
from app.models.session_event import SessionEvent
from app.runtime.execution_authority import ExecutionAuthority


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

    response_action = ResponseAction(
        session_id="session-1",
        agent_id="agent-1",
        risk_level=RiskLevel.MEDIUM,
        response_type=ResponseType.ALERT,
        reason="MEDIUM risk requires alert",
    )

    result = RuntimeResult(
        event=event,
        findings=[finding],
        risk_assessment=risk_assessment,
        response_action=response_action,
    )

    assert result.event == event
    assert result.findings == [finding]
    assert result.risk_assessment == risk_assessment
    assert result.response_action == response_action


def _minimal_result(decision: Decision = Decision.ALLOW, **overrides) -> RuntimeResult:
    return RuntimeResult(
        event=SessionEvent(
            session_id="session-1",
            agent_id="agent-1",
            tool_id="file_read",
            decision=decision,
        ),
        findings=[],
        risk_assessment=RiskAssessment(
            session_id="session-1",
            agent_id="agent-1",
            risk_score=0,
            risk_level=RiskLevel.LOW,
            finding_count=0,
        ),
        response_action=ResponseAction(
            session_id="session-1",
            agent_id="agent-1",
            risk_level=RiskLevel.LOW,
            response_type=ResponseType.MONITOR,
            reason="LOW risk requires monitor",
        ),
        **overrides,
    )


def test_runtime_result_authorization_defaults_to_none():
    result = _minimal_result(decision=Decision.DENY)

    assert result.authorization is None
    assert result.authorized_binding is None
    assert result.authorized_parameters is None


def test_runtime_result_exposes_the_authorized_binding_and_parameters():
    binding = ExecutionBinding.from_operation("file_read", {"path": "notes.txt"})
    grant = ExecutionAuthority().issue(binding, Decision.ALLOW)

    result = _minimal_result(authorization=grant)

    assert result.authorized_binding == binding
    assert result.authorized_parameters == {"path": "notes.txt"}
