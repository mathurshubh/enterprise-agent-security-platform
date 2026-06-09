from datetime import timezone

from app.models.finding import Finding, Severity


def test_finding_creation():
    finding = Finding(
        finding_id="finding-1",
        session_id="session-1",
        agent_id="agent-1",
        rule_name="excessive_tool_usage",
        severity=Severity.HIGH,
        description="Agent exceeded the tool usage threshold",
    )

    assert finding.finding_id == "finding-1"
    assert finding.severity == Severity.HIGH
    assert finding.created_at.tzinfo == timezone.utc
