"""
Shared application-level singletons.

Both the Runtime API and the Enterprise Management API import from this
module so that all services operate on a single, shared in-memory state.
Constructing services in individual router files would produce independent
instances with diverging state.
"""

from app.detection.data_exfiltration_rule import DataExfiltrationRule
from app.detection.prompt_injection_rule import PromptInjectionRule
from app.detection.registry import DetectionRegistry
from app.detection.sensitive_file_access_rule import SensitiveFileAccessRule
from app.registry.tool_registry import ToolRegistry
from app.services.agent_service import AgentService
from app.services.audit_service import AuditService
from app.services.session_service import SessionService
from app.services.tool_inventory_service import ToolInventoryService


def create_default_detection_registry() -> DetectionRegistry:
    """
    Return a DetectionRegistry populated with the platform's active detection rules.

    This function is the single authoritative registration site for all
    detection rules.  Both RuntimeService (via DetectionEngine) and the
    Management API (via DetectionRegistry.metadata()) consume the same
    registry instance, guaranteeing that the management plane always reflects
    the exact rule set used at runtime.
    """
    registry = DetectionRegistry()
    registry.register(PromptInjectionRule())
    registry.register(SensitiveFileAccessRule())
    registry.register(DataExfiltrationRule())
    return registry


# ── Shared singletons ────────────────────────────────────────────────────────

agent_service: AgentService = AgentService()

session_service: SessionService = SessionService()

tool_registry: ToolRegistry = ToolRegistry()

tool_inventory_service: ToolInventoryService = ToolInventoryService(tool_registry)

audit_service: AuditService = AuditService()

detection_registry: DetectionRegistry = create_default_detection_registry()
