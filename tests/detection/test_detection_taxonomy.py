from app.detection.category import DetectionCategory
from app.detection.prompt_injection_rule import PromptInjectionRule
from app.detection.sensitive_file_access_rule import SensitiveFileAccessRule
from app.detection.data_exfiltration_rule import DataExfiltrationRule


def test_rule_categories():
    prompt_rule = PromptInjectionRule()
    sensitive_rule = SensitiveFileAccessRule()
    exfiltration_rule = DataExfiltrationRule()

    # Verify rule names and corresponding broader category mapping
    assert prompt_rule.category == DetectionCategory.PROMPT_SECURITY
    assert sensitive_rule.category == DetectionCategory.DATA_SECURITY
    assert exfiltration_rule.category == DetectionCategory.DATA_SECURITY


def test_category_enum_properties():
    # Verify categories are string enum representations
    assert DetectionCategory.PROMPT_SECURITY == "PROMPT_SECURITY"
    assert DetectionCategory.DATA_SECURITY == "DATA_SECURITY"
    assert DetectionCategory.TOOL_SECURITY == "TOOL_SECURITY"
    assert DetectionCategory.IDENTITY_SECURITY == "IDENTITY_SECURITY"
    assert DetectionCategory.BEHAVIORAL_SECURITY == "BEHAVIORAL_SECURITY"
    assert DetectionCategory.POLICY_SECURITY == "POLICY_SECURITY"
