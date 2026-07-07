import pytest

from app.detection.category import DetectionCategory
from app.detection.prompt_injection_rule import PromptInjectionRule
from app.detection.sensitive_file_access_rule import SensitiveFileAccessRule
from app.detection.registry import DetectionRegistry



def test_detection_registry_workflow():
    registry = DetectionRegistry()

    # Verify initial state is empty
    assert registry.rules() == []
    assert registry.categories() == set()
    assert registry.metadata() == []

    # Register rules
    prompt_rule = PromptInjectionRule()
    sensitive_rule = SensitiveFileAccessRule()

    registry.register(prompt_rule)
    registry.register(sensitive_rule)

    # Verify listing rules
    registered_rules = registry.rules()
    assert len(registered_rules) == 2
    assert prompt_rule in registered_rules
    assert sensitive_rule in registered_rules

    # Verify retrieval
    assert registry.get("PROMPT_INJECTION") is prompt_rule
    assert registry.get("SENSITIVE_FILE_ACCESS") is sensitive_rule

    # Verify category discovery
    assert registry.categories() == {
        DetectionCategory.PROMPT_SECURITY,
        DetectionCategory.DATA_SECURITY,
    }

    # Verify metadata discovery
    all_metadata = registry.metadata()
    assert len(all_metadata) == 2
    assert prompt_rule.metadata in all_metadata
    assert sensitive_rule.metadata in all_metadata


def test_detection_registry_duplicate_registration_fails():
    registry = DetectionRegistry()
    prompt_rule = PromptInjectionRule()

    registry.register(prompt_rule)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(prompt_rule)


def test_detection_registry_get_missing_rule_fails():
    registry = DetectionRegistry()

    with pytest.raises(KeyError, match="not registered"):
        registry.get("NON_EXISTENT_RULE")
