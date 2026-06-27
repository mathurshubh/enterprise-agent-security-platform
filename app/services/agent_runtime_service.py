import uuid
from app.models.agent_runtime_result import (
    AgentRuntimeResult,
)
from app.models.response_action import (
    ResponseType,
)
from app.auth.authorization_service import (
    AuthorizationService,
)
from app.models.agent import (
    Agent,
    AgentStatus,
    RiskTier,
)
from app.models.audit_event import Decision

from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel

from app.policy.policy_engine import PolicyEngine
from app.services.agent_service import AgentService
from app.services.detection_service import (
    DetectionService,
)
from app.services.response_service import (
    ResponseService,
)
from app.services.risk_service import RiskService
from app.services.runtime_service import RuntimeService
from app.services.session_service import (
    SessionService,
)
from app.services.tool_service import ToolService
from app.tools.directory_list_tool import (
    DirectoryListTool,
)
from app.tools.file_read_tool import (
    FileReadTool,
)

from app.agents.enterprise_agent import EnterpriseAgent
from app.services.ollama_agent import OllamaAgent

from app.providers.provider_factory import ProviderFactory

class AgentRuntimeService:
    _AGENT_ID = "agent-1"
    _WORKSPACE_ROOT = "demo_workspace"

    def __init__(
        self,
        agent: EnterpriseAgent | None = None,
    ) -> None:
        if agent is None:
            provider = ProviderFactory.create()
            self._agent = OllamaAgent(provider)
        else:
            self._agent = agent

        self._file_read_tool = FileReadTool(
            self._WORKSPACE_ROOT
        )

        self._directory_list_tool = (
            DirectoryListTool(
                self._WORKSPACE_ROOT
            )
        )

        agent_service = AgentService()
        tool_service = ToolService()
        session_service = SessionService()

        self._register_default_agent(
            agent_service
        )

        self._register_default_tools(
            tool_service
        )

        authorization_service = (
            AuthorizationService(
                agent_service,
                tool_service,
                PolicyEngine(),
            )
        )

        self._runtime_service = RuntimeService(
            authorization_service,
            session_service,
            DetectionService(),
            RiskService(),
            ResponseService(),
        )

    @classmethod
    def _register_default_agent(
        cls,
        agent_service: AgentService,
    ) -> None:
        agent_service.register_agent(
            Agent(
                agent_id=cls._AGENT_ID,
                name="Local Agent",
                owner="security-team",
                risk_tier=RiskTier.HIGH,
                approved_tools=[
                    "file_read",
                    "directory_list",
                ],
                status=AgentStatus.ACTIVE,
            )
        )

    @classmethod
    def _register_default_tools(
        cls,
        tool_service: ToolService,
    ) -> None:
        tool_service.register_tool(
            cls._create_filesystem_tool(
                tool_id="file_read",
                name="File Read",
                description="Read files from the workspace",
                required_permission="files:read",
            )
        )

        tool_service.register_tool(
            cls._create_filesystem_tool(
                tool_id="directory_list",
                name="Directory List",
                description="List files in the workspace",
                required_permission="files:list",
            )
        )

    @staticmethod
    def _create_filesystem_tool(
        tool_id: str,
        name: str,
        description: str,
        required_permission: str,
    ) -> Tool:
        return Tool(
            metadata=ToolMetadata(
                identity=ToolIdentity(
                    tool_id=tool_id,
                    name=name,
                    description=description,
                ),
                governance=ToolGovernance(
                    risk_level=ToolRiskLevel.LOW,
                    required_permissions=[
                        required_permission,
                    ],
                ),
                capability=ToolCapability(
                    category="filesystem",
                    reads_files=True,
                ),
                operational=ToolOperational(),
            )
        )

    def execute(
        self,
        query: str,
    ) -> AgentRuntimeResult:
        invocation = self._agent.invoke(query)

        resource = (
            invocation.parameters.get(
                "path"
            )
        )

        session_id = str(
            uuid.uuid4()
        )

        runtime_result = (
            self._runtime_service.execute(
                session_id=session_id,
                agent_id=self._AGENT_ID,
                tool_id=invocation.tool_id,
                resource=resource,
            )
        )

        decision = (
            runtime_result.event.decision
        )

        response_type = (
            runtime_result.response_action.response_type
        )

        if (
            decision == Decision.DENY
            or response_type
            != ResponseType.MONITOR
        ):
            return AgentRuntimeResult(
                decision=decision.value,
                response_type=response_type,
                output=None,
            )

        if invocation.tool_id == "file_read":
            output = self._file_read_tool.read(
                invocation.parameters[
                    "path"
                ]
            )

            return AgentRuntimeResult(
                decision=decision.value,
                response_type=response_type,
                output=output,
            )

        if invocation.tool_id == "directory_list":
            output = (
                self._directory_list_tool
                .list_directory(
                    invocation.parameters[
                        "path"
                    ]
                )
            )

            return AgentRuntimeResult(
                decision=decision.value,
                response_type=response_type,
                output=output,
            )

        raise ValueError(
            f"Unsupported tool: "
            f"{invocation.tool_id}"
        )
