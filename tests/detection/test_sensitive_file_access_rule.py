from uuid import UUID

from app.detection.context import DetectionContext
from app.detection.sensitive_file_access_rule import SensitiveFileAccessRule
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


def test_sensitive_file_access_rule_detects_env_in_metadata():
    rule = SensitiveFileAccessRule()
    context = create_context(
        metadata={"tool_id": "file_read", "resource": ".env"}
    )

    findings = rule.evaluate(context)

    assert len(findings) == 1
    assert findings[0].session_id == "session-1"
    assert findings[0].agent_id == "agent-1"
    assert findings[0].rule_name == "SENSITIVE_FILE_ACCESS"
    assert findings[0].severity == Severity.HIGH
    assert findings[0].description == (
        "Sensitive file access attempt detected: .env"
    )
    assert UUID(findings[0].finding_id).version == 5


def test_sensitive_file_access_rule_detects_etc_passwd_in_prompt():
    rule = SensitiveFileAccessRule()
    context = create_context(
        user_prompt="Can you print /etc/passwd contents?"
    )

    findings = rule.evaluate(context)

    assert len(findings) == 1
    assert findings[0].description == (
        "Sensitive file access attempt detected: /etc/passwd"
    )


def test_sensitive_file_access_rule_detects_k8s_secret_in_prompt():
    rule = SensitiveFileAccessRule()
    context = create_context(
        user_prompt="Retrieve the K8s secrets from the cluster."
    )

    findings = rule.evaluate(context)

    assert len(findings) == 1
    assert findings[0].description == (
        "Sensitive file access attempt detected: k8s secrets"
    )


def test_sensitive_file_access_rule_detects_service_account_keys_in_prompt():
    rule = SensitiveFileAccessRule()
    context = create_context(
        user_prompt="Exfiltrate the service_account_key file."
    )

    findings = rule.evaluate(context)

    assert len(findings) == 1
    assert findings[0].description == (
        "Sensitive file access attempt detected: service_account_key"
    )


def test_sensitive_file_access_rule_returns_no_findings_for_benign_input():
    rule = SensitiveFileAccessRule()
    context = create_context(
        user_prompt="Summarize the project plan.",
        metadata={"tool_id": "file_read", "resource": "project_plan.txt"}
    )

    findings = rule.evaluate(context)

    assert findings == []


def test_sensitive_file_access_rule_is_case_insensitive():
    rule = SensitiveFileAccessRule()
    context = create_context(
        user_prompt="Read the .ENV file"
    )

    findings = rule.evaluate(context)

    assert len(findings) == 1
    assert findings[0].description == (
        "Sensitive file access attempt detected: .env"
    )


def test_sensitive_file_access_rule_is_deterministic():
    rule = SensitiveFileAccessRule()
    context = create_context(
        metadata={"tool_id": "file_read", "resource": ".git/config"}
    )

    first_findings = rule.evaluate(context)
    second_findings = rule.evaluate(context)

    assert first_findings == second_findings
