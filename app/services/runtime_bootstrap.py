from pathlib import Path

from app.auth.authorization_service import AuthorizationService
from app.detection.data_exfiltration_rule import DataExfiltrationRule
from app.detection.engine import DetectionEngine
from app.detection.prompt_injection_rule import PromptInjectionRule
from app.detection.registry import DetectionRegistry
from app.detection.sensitive_file_access_rule import SensitiveFileAccessRule
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.policy.policy_engine import PolicyEngine
from app.registry.tool_registry import ToolRegistry
from app.repositories.in_memory.tool_repository import InMemoryToolRepository
from app.repositories.interfaces.tool_repository import ToolRepository
from app.runtime.execution_authority import ExecutionAuthority
from app.services.agent_lock_manager import AgentLockManager
from app.services.agent_service import AgentNotFoundError, AgentService
from app.services.audit_service import AuditService
from app.services.detection_service import DetectionService
from app.services.findings_service import FindingsService
from app.services.response_service import ResponseService
from app.services.risk_aggregator import RiskAggregator
from app.services.risk_service import RiskService
from app.services.runtime_service import (
    IncompleteRuntimeConfigurationError,
    RuntimeService,
)
from app.services.session_service import SessionService
from app.services.tool_service import ToolNotFoundError, ToolService
from app.telemetry.contracts import TelemetryEmitter
from app.tools.directory_list_tool import DirectoryListTool
from app.tools.file_read_tool import FileReadTool


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


def register_default_agent(
    agent_service: AgentService, agent_id: str = "agent-1"
) -> None:
    """Register the platform's default agent if it is not already registered."""
    try:
        agent_service.get_agent(agent_id)
    except AgentNotFoundError:
        agent_service.register_agent(
            Agent(
                agent_id=agent_id,
                name="Local Agent",
                owner="security-team",
                risk_tier=RiskTier.HIGH,
                approved_tools=["file_read", "directory_list"],
                status=AgentStatus.ACTIVE,
            )
        )


def register_default_tools(
    tool_service: ToolService,
    tool_registry: ToolRegistry | None = None,
) -> None:
    """Register default filesystem security tools metadata and executable tool instances."""
    try:
        tool_service.get_tool("file_read")
    except ToolNotFoundError:
        tool_service.register_tool(
            Tool(
                metadata=ToolMetadata(
                    identity=ToolIdentity(
                        tool_id="file_read",
                        name="File Read",
                        description="Read files from the workspace",
                    ),
                    governance=ToolGovernance(
                        risk_level=ToolRiskLevel.LOW,
                        required_permissions=["files:read"],
                    ),
                    capability=ToolCapability(
                        category="filesystem",
                        reads_files=True,
                    ),
                    operational=ToolOperational(),
                )
            )
        )

    try:
        tool_service.get_tool("directory_list")
    except ToolNotFoundError:
        tool_service.register_tool(
            Tool(
                metadata=ToolMetadata(
                    identity=ToolIdentity(
                        tool_id="directory_list",
                        name="Directory List",
                        description="List files in the workspace",
                    ),
                    governance=ToolGovernance(
                        risk_level=ToolRiskLevel.LOW,
                        required_permissions=["files:list"],
                    ),
                    capability=ToolCapability(
                        category="filesystem",
                        reads_files=True,
                    ),
                    operational=ToolOperational(),
                )
            )
        )

    if tool_registry is not None:
        workspace_root = Path("demo_workspace")
        if not tool_registry.exists("file_read"):
            tool_registry.register(FileReadTool(workspace_root))
        if not tool_registry.exists("directory_list"):
            tool_registry.register(DirectoryListTool(workspace_root))


def bootstrap_runtime_service(
    agent_service: AgentService,
    session_service: SessionService,
    audit_service: AuditService,
    detection_registry: DetectionRegistry,
    agent_id: str = "agent-1",
    tool_registry: ToolRegistry | None = None,
    tool_service: ToolService | None = None,
    tool_repository: ToolRepository | None = None,
    findings_service: FindingsService | None = None,
    risk_service: RiskService | None = None,
    telemetry_emitter: TelemetryEmitter | None = None,
    execution_authority: ExecutionAuthority | None = None,
    risk_aggregator: RiskAggregator | None = None,
    lock_manager: AgentLockManager | None = None,
) -> RuntimeService:
    """Canonical bootstrapping implementation for RuntimeService and dependencies."""
    register_default_agent(agent_service, agent_id)

    registry = tool_registry or ToolRegistry()
    active_tool_service = tool_service or ToolService(
        tool_repository=tool_repository or InMemoryToolRepository(),
        tool_registry=registry,
    )
    register_default_tools(active_tool_service, registry)

    policy_engine = PolicyEngine()
    authorization_service = AuthorizationService(
        agent_service=agent_service,
        tool_service=active_tool_service,
        policy_engine=policy_engine,
    )

    detection_engine = DetectionEngine(detection_registry.rules())
    detection_service_instance = DetectionService()

    if session_service is None:
        raise IncompleteRuntimeConfigurationError(
            "RuntimeService requires an explicit SessionService dependency"
        )

    return RuntimeService(
        authorization_service=authorization_service,
        session_service=session_service,
        detection_engine=detection_engine,
        detection_service=detection_service_instance,
        risk_service=risk_service or RiskService(),
        response_service=ResponseService(),
        audit_service=audit_service,
        tool_registry=registry,
        findings_service=findings_service,
        telemetry_emitter=telemetry_emitter,
        execution_authority=execution_authority,
        # M2b: enforcement posture is agent-scoped, so the pipeline needs the agent
        # registry that owns enforcement state.
        agent_service=agent_service,
        # M5-B.5: RiskAggregator is the sole authority for agent enforcement posture,
        # and RuntimeService refuses to exist without one. Bootstrapping supplies a
        # default rather than leaving the caller to produce an unusable runtime.
        risk_aggregator=risk_aggregator or RiskAggregator(),
        lock_manager=lock_manager,
    )
