from app.detection.engine import DetectionEngine
from app.detection.registry import DetectionRegistry
from app.models.platform_capabilities import PlatformCapabilities
from app.registry.tool_registry import ToolRegistry
from app.services.detection_service import DetectionService


class CapabilityService:
    """Lightweight service for runtime platform capability discovery.

    Aggregates runtime capabilities dynamically from ToolRegistry, DetectionRegistry / DetectionEngine,
    and DetectionService without maintaining hardcoded capability lists or duplicating metadata.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        detection_registry: DetectionRegistry | None = None,
        detection_engine: DetectionEngine | None = None,
        detection_service: DetectionService | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._detection_registry = detection_registry
        self._detection_engine = detection_engine
        self._detection_service = detection_service or DetectionService()

    def discover(self) -> PlatformCapabilities:
        """Discover current runtime capabilities dynamically from authoritative platform singletons."""
        tools: set[str] = set()
        if self._tool_registry:
            tools = self._tool_registry.list_tool_ids()

        content_rules: set[str] = set()
        if self._detection_registry:
            content_rules = self._detection_registry.list_rule_names()
        elif self._detection_engine:
            content_rules = self._detection_engine.list_rule_names()

        behavioral_rules: set[str] = set()
        if self._detection_service:
            behavioral_rules = self._detection_service.registered_rule_names()

        return PlatformCapabilities(
            tools=tools,
            content_detection_rules=content_rules,
            behavioral_detection_rules=behavioral_rules,
        )
