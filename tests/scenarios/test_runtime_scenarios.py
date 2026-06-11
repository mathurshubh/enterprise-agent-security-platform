from app.models.risk_assessment import RiskLevel
from tests.services.test_runtime_service import (
    create_runtime_service,
)



def test_normal_runtime_scenario():
    service, _ = create_runtime_service(["file_read"])

    result = service.execute(
        session_id="scenario-session-1",
        agent_id="agent-1",
        tool_id="file_read",
    )

    assert result.findings == []
    assert (
        result.risk_assessment.risk_level
        == RiskLevel.LOW
    )
    assert (
        result.risk_assessment.finding_count == 0
    )



def test_excessive_denial_runtime_scenario():
    service, _ = create_runtime_service([])

    service.execute(
        session_id="scenario-session-2",
        agent_id="agent-1",
        tool_id="file_read",
    )
    service.execute(
        session_id="scenario-session-2",
        agent_id="agent-1",
        tool_id="file_read",
    )
    result = service.execute(
        session_id="scenario-session-2",
        agent_id="agent-1",
        tool_id="file_read",
    )

    assert len(result.findings) == 1
    assert (
        result.findings[0].rule_name
        == "EXCESSIVE_DENIALS"
    )
    assert (
        result.risk_assessment.risk_level
        == RiskLevel.MEDIUM
    )
    assert (
        result.risk_assessment.finding_count == 1
    )



def test_mixed_behavior_runtime_scenario():
    service, _ = create_runtime_service(["file_read"])

    result = service.execute(
        session_id="scenario-session-3",
        agent_id="agent-1",
        tool_id="file_read",
    )

    assert result.findings == []
    assert (
        result.risk_assessment.risk_level
        == RiskLevel.LOW
    )
