from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.services.agent_service import AgentService
from app.services.tool_service import ToolService
from app.auth.authorization_service import AuthorizationService
from app.policy.policy_engine import PolicyEngine
from app.detection.engine import DetectionEngine
from app.detection.registry import DetectionRegistry
from app.services.detection_service import DetectionService
from app.services.risk_service import RiskService
from app.services.response_service import ResponseService
from app.services.audit_service import AuditService
from app.services.session_service import SessionService
from app.services.runtime_service import RuntimeService


def register_default_agent(agent_service: AgentService, agent_id: str = "agent-1") -> None:
    """Register the platform's default agent if it is not already registered."""
    try:
        agent_service.get_agent(agent_id)
    except Exception:
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


def register_default_tools(tool_service: ToolService) -> None:
    """Register default filesystem security tools metadata."""
    try:
        tool_service.get_tool("file_read")
    except Exception:
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
    except Exception:
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


def bootstrap_runtime_service(
    agent_service: AgentService,
    session_service: SessionService,
    audit_service: AuditService,
    detection_registry: DetectionRegistry,
    agent_id: str = "agent-1",
) -> RuntimeService:
    """Canonical bootstrapping implementation for RuntimeService and dependencies."""
    register_default_agent(agent_service, agent_id)

    tool_service = ToolService()
    register_default_tools(tool_service)

    policy_engine = PolicyEngine()
    authorization_service = AuthorizationService(
        agent_service=agent_service,
        tool_service=tool_service,
        policy_engine=policy_engine,
    )

    detection_engine = DetectionEngine(detection_registry.rules())

    return RuntimeService(
        authorization_service=authorization_service,
        session_service=session_service,
        detection_engine=detection_engine,
        detection_service=DetectionService(),
        risk_service=RiskService(),
        response_service=ResponseService(),
        audit_service=audit_service,
    )
