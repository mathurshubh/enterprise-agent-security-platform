from app.detection.category import DetectionCategory
from app.detection.prompt_injection_rule import PromptInjectionRule
from app.detection.sensitive_file_access_rule import SensitiveFileAccessRule
from app.detection.data_exfiltration_rule import DataExfiltrationRule


def test_rule_categories_and_metadata():
    prompt_rule = PromptInjectionRule()
    sensitive_rule = SensitiveFileAccessRule()
    exfiltration_rule = DataExfiltrationRule()

    # Verify legacy rule names and category mapping
    assert prompt_rule.rule_name == "PROMPT_INJECTION"
    assert prompt_rule.category == DetectionCategory.PROMPT_SECURITY

    assert sensitive_rule.rule_name == "SENSITIVE_FILE_ACCESS"
    assert sensitive_rule.category == DetectionCategory.DATA_SECURITY

    assert exfiltration_rule.rule_name == "DATA_EXFILTRATION"
    assert exfiltration_rule.category == DetectionCategory.DATA_SECURITY

    # Verify new RuleMetadata properties
    assert prompt_rule.metadata.name == "PROMPT_INJECTION"
    assert prompt_rule.metadata.category == DetectionCategory.PROMPT_SECURITY
    assert prompt_rule.metadata.description == "Detects common deterministic prompt injection indicators."

    assert sensitive_rule.metadata.name == "SENSITIVE_FILE_ACCESS"
    assert sensitive_rule.metadata.category == DetectionCategory.DATA_SECURITY
    assert "access to sensitive files" in sensitive_rule.metadata.description

    assert exfiltration_rule.metadata.name == "DATA_EXFILTRATION"
    assert exfiltration_rule.metadata.category == DetectionCategory.DATA_SECURITY
    assert "data exfiltration attempts" in exfiltration_rule.metadata.description


def test_category_enum_properties():
    # Verify categories are string enum representations
    assert DetectionCategory.PROMPT_SECURITY == "PROMPT_SECURITY"
    assert DetectionCategory.DATA_SECURITY == "DATA_SECURITY"
    assert DetectionCategory.TOOL_SECURITY == "TOOL_SECURITY"
    assert DetectionCategory.IDENTITY_SECURITY == "IDENTITY_SECURITY"
    assert DetectionCategory.BEHAVIORAL_SECURITY == "BEHAVIORAL_SECURITY"
    assert DetectionCategory.POLICY_SECURITY == "POLICY_SECURITY"

