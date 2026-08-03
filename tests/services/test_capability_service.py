from app.detection.data_exfiltration_rule import DataExfiltrationRule
from app.detection.engine import DetectionEngine
from app.detection.prompt_injection_rule import PromptInjectionRule
from app.detection.registry import DetectionRegistry
from app.detection.sensitive_file_access_rule import SensitiveFileAccessRule
from app.registry.tool_registry import ToolRegistry
from app.services.capability_service import CapabilityService
from app.services.detection_service import DetectionService
from app.tools.file_read_tool import FileReadTool


def test_tool_registry_list_tool_ids():
    registry = ToolRegistry()
    assert registry.list_tool_ids() == set()

    tool = FileReadTool("/tmp")
    registry.register(tool)
    assert registry.list_tool_ids() == {"file_read"}


def test_detection_registry_list_rule_names():
    registry = DetectionRegistry()
    registry.register(PromptInjectionRule())
    registry.register(SensitiveFileAccessRule())
    registry.register(DataExfiltrationRule())

    assert registry.list_rule_names() == {
        "PROMPT_INJECTION",
        "SENSITIVE_FILE_ACCESS",
        "DATA_EXFILTRATION",
    }


def test_detection_engine_list_rule_names():
    engine = DetectionEngine([PromptInjectionRule(), DataExfiltrationRule()])
    assert engine.list_rule_names() == {"PROMPT_INJECTION", "DATA_EXFILTRATION"}


def test_detection_service_registered_rule_names():
    service = DetectionService()
    assert service.registered_rule_names() == {"EXCESSIVE_DENIALS"}


def test_capability_service_discover():
    tool_reg = ToolRegistry()
    tool_reg.register(FileReadTool("/tmp"))

    det_reg = DetectionRegistry()
    det_reg.register(PromptInjectionRule())
    det_reg.register(DataExfiltrationRule())

    det_service = DetectionService()

    cap_service = CapabilityService(
        tool_registry=tool_reg,
        detection_registry=det_reg,
        detection_service=det_service,
    )

    capabilities = cap_service.discover()

    assert capabilities.tools == {"file_read"}
    assert capabilities.content_detection_rules == {
        "PROMPT_INJECTION",
        "DATA_EXFILTRATION",
    }
    assert capabilities.behavioral_detection_rules == {"EXCESSIVE_DENIALS"}
    assert capabilities.all_detection_rules == {
        "PROMPT_INJECTION",
        "DATA_EXFILTRATION",
        "EXCESSIVE_DENIALS",
    }
