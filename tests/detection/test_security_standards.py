from app.detection.category import DetectionCategory
from app.detection.metadata import RuleMetadata
from app.detection.prompt_injection_rule import PromptInjectionRule
from app.detection.sensitive_file_access_rule import SensitiveFileAccessRule
from app.detection.data_exfiltration_rule import DataExfiltrationRule
from app.detection.security_standard import SecurityControlReference, SecurityFramework


def test_security_control_reference_instantiation():
    ref = SecurityControlReference(
        framework=SecurityFramework.OWASP_LLM,
        control_id="LLM01",
        title="Prompt Injection",
    )
    assert ref.framework == SecurityFramework.OWASP_LLM
    assert ref.control_id == "LLM01"
    assert ref.title == "Prompt Injection"


def test_rule_metadata_defaults_controls():
    meta = RuleMetadata(
        name="TEST_RULE",
        category=DetectionCategory.PROMPT_SECURITY,
        description="Testing default controls",
    )
    assert meta.controls == ()


def test_rule_security_mappings():
    prompt_rule = PromptInjectionRule()
    sensitive_rule = SensitiveFileAccessRule()
    exfiltration_rule = DataExfiltrationRule()

    # PromptInjectionRule assertions
    prompt_controls = prompt_rule.metadata.controls
    assert len(prompt_controls) == 2

    owasp_ref = next(c for c in prompt_controls if c.framework == SecurityFramework.OWASP_LLM)
    assert owasp_ref.control_id == "LLM01"
    assert owasp_ref.title == "Prompt Injection"

    mitre_ref = next(c for c in prompt_controls if c.framework == SecurityFramework.MITRE_ATLAS)
    assert mitre_ref.control_id == "AML.T0043"
    assert mitre_ref.title == "User Prompt Injection"

    # SensitiveFileAccessRule assertions
    sensitive_controls = sensitive_rule.metadata.controls
    assert len(sensitive_controls) == 1
    assert sensitive_controls[0].framework == SecurityFramework.MITRE_ATTACK
    assert sensitive_controls[0].control_id == "T1083"
    assert sensitive_controls[0].title == "File and Directory Discovery"

    # DataExfiltrationRule assertions
    exfiltration_controls = exfiltration_rule.metadata.controls
    assert len(exfiltration_controls) == 1
    assert exfiltration_controls[0].framework == SecurityFramework.MITRE_ATTACK
    assert exfiltration_controls[0].control_id == "T1048"
    assert exfiltration_controls[0].title == "Exfiltration Over Alternative Protocol"
