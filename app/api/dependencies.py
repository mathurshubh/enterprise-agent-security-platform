"""
Shared application-level singletons.

Both the Runtime API and the Enterprise Management API import from this
module so that all services operate on a single, shared in-memory state.
Constructing services in individual router files would produce independent
instances with diverging state.
"""

from app.auth.jwt_service import JWTService
from app.config.settings import get_jwt_secret_key, get_max_terminal_execution_receipts
from app.detection.registry import DetectionRegistry
from app.models.detection_retention import DetectionRetentionPolicy
from app.models.execution_evidence_retention import (
    ExecutionEvidenceRetentionPolicy,
)
from app.registry.scenario_registry import ScenarioRegistry
from app.registry.tool_registry import ToolRegistry
from app.repositories.in_memory import (
    InMemoryAdministrativeStateRepository,
    InMemoryAgentRepository,
    InMemoryApprovalContinuationRepository,
    InMemoryAuditEvidenceRepository,
    InMemoryEnforcementStateRepository,
    InMemorySessionRepository,
    InMemoryToolRepository,
)
from app.runtime.execution_authority import ExecutionAuthority
from app.services.agent_lock_manager import AgentLockManager
from app.services.agent_service import AgentService
from app.services.attack_scenario_service import AttackScenarioService
from app.services.audit_service import AuditService
from app.services.capability_service import CapabilityService
from app.services.detection_service import DetectionService
from app.services.enforcement_coordinator import EnforcementCoordinator
from app.services.execution_evidence_service import ExecutionEvidenceService
from app.services.execution_reconciler import ExecutionReconciler
from app.services.findings_service import FindingsService
from app.services.risk_aggregator import RiskAggregator
from app.services.risk_service import RiskService
from app.services.runtime_bootstrap import (
    bootstrap_runtime_service,
    create_default_detection_registry,
)
from app.services.runtime_service import RuntimeService
from app.services.session_service import SessionService
from app.services.tool_inventory_service import ToolInventoryService
from app.services.tool_service import ToolService
from app.telemetry.dispatcher import InMemoryTelemetryDispatcher

# ── Shared repository singletons (ADR-030 composition root) ──────────────────

agent_repository: InMemoryAgentRepository = InMemoryAgentRepository()
enforcement_repository: InMemoryEnforcementStateRepository = (
    InMemoryEnforcementStateRepository()
)
administrative_repository: InMemoryAdministrativeStateRepository = (
    InMemoryAdministrativeStateRepository()
)
audit_repository: InMemoryAuditEvidenceRepository = InMemoryAuditEvidenceRepository()
session_repository: InMemorySessionRepository = InMemorySessionRepository()
tool_repository: InMemoryToolRepository = InMemoryToolRepository()
approval_grant_repository: InMemoryApprovalContinuationRepository = (
    InMemoryApprovalContinuationRepository()
)

# ── Shared service singletons ────────────────────────────────────────────────

agent_service: AgentService = AgentService(
    agent_repository=agent_repository,
    enforcement_repository=enforcement_repository,
    administrative_repository=administrative_repository,
)

detection_retention_policy: DetectionRetentionPolicy = (
    DetectionRetentionPolicy.from_detection_service(DetectionService())
)

session_service: SessionService = SessionService(
    retention_policy=detection_retention_policy,
    session_repository=session_repository,
)

tool_registry: ToolRegistry = ToolRegistry()

tool_service: ToolService = ToolService(
    tool_repository=tool_repository,
    tool_registry=tool_registry,
)

tool_inventory_service: ToolInventoryService = ToolInventoryService(tool_registry)

audit_service: AuditService = AuditService(
    audit_repository=audit_repository,
)

findings_service: FindingsService = FindingsService()

risk_service: RiskService = RiskService()

agent_lock_manager: AgentLockManager = AgentLockManager()

risk_aggregator: RiskAggregator = RiskAggregator()

detection_registry: DetectionRegistry = create_default_detection_registry()

scenario_registry: ScenarioRegistry = AttackScenarioService().load_registry()

telemetry_dispatcher: InMemoryTelemetryDispatcher = InMemoryTelemetryDispatcher()

# ADR-023: the single issuer of execution grants for this process. Every executor
# that runs tools on behalf of the shared runtime must verify against it.
execution_authority: ExecutionAuthority = ExecutionAuthority()

# ADR-032 §12: the authoritative execution evidence store for the live runtime. One
# instance per composition root — the scenario pipeline gets its own, because scenario
# activity must not enter live security state (ADR-013 M2a).
#
# Capacity is a deployment decision, so it comes from configuration; the policy itself
# is a required argument, which is what makes an unbounded store unrepresentable rather
# than merely discouraged.
execution_evidence_store: ExecutionEvidenceService = ExecutionEvidenceService(
    retention_policy=ExecutionEvidenceRetentionPolicy(
        max_terminal_receipts=get_max_terminal_execution_receipts(),
    )
)

# ADR-032 §12: the recovery boundary for the live evidence plane. Constructed here
# against the one live store — not in the lifespan hook, which must operate on the
# composition root's store rather than building a second evidence plane of its own.
#
# Reconciliation itself runs at startup (app/main.py), never at import: security
# lifecycle ordering must not be an accidental consequence of module import order.
execution_reconciler: ExecutionReconciler = ExecutionReconciler(
    evidence_store=execution_evidence_store
)

runtime_service: RuntimeService = bootstrap_runtime_service(
    agent_service=agent_service,
    session_service=session_service,
    audit_service=audit_service,
    tool_service=tool_service,
    detection_registry=detection_registry,
    tool_registry=tool_registry,
    findings_service=findings_service,
    risk_service=risk_service,
    telemetry_emitter=telemetry_dispatcher,
    execution_authority=execution_authority,
    evidence_store=execution_evidence_store,
    risk_aggregator=risk_aggregator,
    lock_manager=agent_lock_manager,
)

# M2b: recovery from containment runs only through this coordinator. The runtime may
# contain an agent; it never returns one to service.
enforcement_coordinator: EnforcementCoordinator = EnforcementCoordinator(
    agent_service=agent_service,
    execution_authority=execution_authority,
    findings_service=findings_service,
    risk_aggregator=risk_aggregator,
    lock_manager=agent_lock_manager,
    # Allocation authority for the agent-sequence half of the enforcement baseline.
    # Without it a reinstatement records 0 there and excludes no prior event.
    session_service=session_service,
)

capability_service: CapabilityService = CapabilityService(
    tool_registry=tool_registry,
    detection_registry=detection_registry,
    detection_service=runtime_service.detection_service,
)

jwt_service: JWTService = JWTService(
    secret_key=get_jwt_secret_key(),
)
