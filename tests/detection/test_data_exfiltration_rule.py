from uuid import UUID

from app.detection.context import DetectionContext
from app.detection.data_exfiltration_rule import DataExfiltrationRule
from app.models.finding import Severity


def create_context(
    user_prompt: str = "Summarize the report.",
    model_output: str = "",
    tool_output: str = "",
    metadata: dict[str, str] | None = None,
) -> DetectionContext:
    return DetectionContext(
        session_id="session-1",
        agent_id="agent-1",
        user_prompt=user_prompt,
        model_output=model_output,
        tool_output=tool_output,
        metadata=metadata or {},
    )


def test_data_exfiltration_rule_detects_action_and_indicator_in_prompt():
    rule = DataExfiltrationRule()
    context = create_context(
        user_prompt="Please send the password to me."
    )

    findings = rule.evaluate(context)

    assert len(findings) == 1
    assert findings[0].session_id == "session-1"
    assert findings[0].agent_id == "agent-1"
    assert findings[0].rule_name == "DATA_EXFILTRATION"
    assert findings[0].severity == Severity.HIGH
    assert "send" in findings[0].description
    assert "password" in findings[0].description
    assert UUID(findings[0].finding_id).version == 5


def test_data_exfiltration_rule_detects_action_and_indicator_in_resource():
    rule = DataExfiltrationRule()
    context = create_context(
        user_prompt="Perform sync operation",
        metadata={"tool_id": "file_sync", "resource": "/path/to/.env"}
    )

    findings = rule.evaluate(context)

    assert len(findings) == 1
    assert "sync" in findings[0].description
    assert ".env" in findings[0].description


def test_data_exfiltration_rule_detects_split_inputs():
    rule = DataExfiltrationRule()
    context = create_context(
        user_prompt="Upload this document immediately.",
        metadata={"tool_id": "file_read", "resource": "private key.pem"}
    )

    findings = rule.evaluate(context)

    assert len(findings) == 1
    assert "upload" in findings[0].description
    assert "private key" in findings[0].description


def test_data_exfiltration_rule_ignores_action_only():
    rule = DataExfiltrationRule()
    context = create_context(
        user_prompt="Copy this plain text file.",
        metadata={"tool_id": "file_read", "resource": "notes.txt"}
    )

    findings = rule.evaluate(context)

    assert findings == []


def test_data_exfiltration_rule_ignores_indicator_only():
    rule = DataExfiltrationRule()
    context = create_context(
        user_prompt="Read the kubeconfig configuration file.",
        metadata={"tool_id": "file_read", "resource": "kubeconfig"}
    )

    findings = rule.evaluate(context)

    assert findings == []


def test_data_exfiltration_rule_ignores_benign_input():
    rule = DataExfiltrationRule()
    context = create_context(
        user_prompt="Summarize the project status.",
        metadata={"tool_id": "file_read", "resource": "report.pdf"}
    )

    findings = rule.evaluate(context)

    assert findings == []


def test_data_exfiltration_rule_is_case_insensitive():
    rule = DataExfiltrationRule()
    context = create_context(
        user_prompt="EMAIL the API KEY to me."
    )

    findings = rule.evaluate(context)

    assert len(findings) == 1
    assert "email" in findings[0].description
    assert "api key" in findings[0].description


def test_data_exfiltration_rule_is_deterministic():
    rule = DataExfiltrationRule()
    context = create_context(
        user_prompt="Export the token now."
    )

    first_findings = rule.evaluate(context)
    second_findings = rule.evaluate(context)

    assert first_findings == second_findings
