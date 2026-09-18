"""
Shared application-level singletons.

Both the Runtime API and the Enterprise Management API import from this
module so that all services operate on a single, shared in-memory state.
Constructing services in individual router files would produce independent
instances with diverging state.
"""

from app.auth.jwt_service import JWTService
from app.config.settings import get_jwt_secret_key
from app.detection.registry import DetectionRegistry
from app.registry.scenario_registry import ScenarioRegistry
from app.registry.tool_registry import ToolRegistry
from app.runtime.execution_authority import ExecutionAuthority
from app.services.agent_service import AgentService
from app.services.attack_scenario_service import AttackScenarioService
from app.services.audit_service import AuditService
from app.services.capability_service import CapabilityService
from app.services.findings_service import FindingsService
from app.services.risk_service import RiskService
from app.services.runtime_bootstrap import (
    bootstrap_runtime_service,
    create_default_detection_registry,
)
from app.services.runtime_service import RuntimeService
from app.services.session_service import SessionService
from app.services.tool_inventory_service import ToolInventoryService
from app.telemetry.dispatcher import InMemoryTelemetryDispatcher

# ── Shared singletons ────────────────────────────────────────────────────────

agent_service: AgentService = AgentService()

session_service: SessionService = SessionService()

tool_registry: ToolRegistry = ToolRegistry()

tool_inventory_service: ToolInventoryService = ToolInventoryService(tool_registry)

audit_service: AuditService = AuditService()

findings_service: FindingsService = FindingsService()

risk_service: RiskService = RiskService()

detection_registry: DetectionRegistry = create_default_detection_registry()

scenario_registry: ScenarioRegistry = AttackScenarioService().load_registry()

telemetry_dispatcher: InMemoryTelemetryDispatcher = InMemoryTelemetryDispatcher()

# ADR-023: the single issuer of execution grants for this process. Every executor
# that runs tools on behalf of the shared runtime must verify against it.
execution_authority: ExecutionAuthority = ExecutionAuthority()

runtime_service: RuntimeService = bootstrap_runtime_service(
    agent_service=agent_service,
    session_service=session_service,
    audit_service=audit_service,
    detection_registry=detection_registry,
    tool_registry=tool_registry,
    findings_service=findings_service,
    risk_service=risk_service,
    telemetry_emitter=telemetry_dispatcher,
    execution_authority=execution_authority,
)

capability_service: CapabilityService = CapabilityService(
    tool_registry=tool_registry,
    detection_registry=detection_registry,
    detection_service=runtime_service.detection_service,
)

jwt_service: JWTService = JWTService(
    secret_key=get_jwt_secret_key(),
)
