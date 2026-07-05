import uuid
from typing import Protocol

from app.models.agent_runtime_result import (
    AgentRuntimeResult,
)
from app.models.runtime_result import RuntimeResult
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
from app.registry.tool_registry import ToolRegistry
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

from app.detection.engine import DetectionEngine
from app.detection.prompt_injection_rule import PromptInjectionRule


class RuntimeExecutor(Protocol):
    def execute(
        self,
        session_id: str,
        agent_id: str,
        tool_id: str,
        resource: str | None = None,
        user_prompt: str = "",
        model_output: str = "",
        tool_output: str = "",
    ) -> RuntimeResult:
        """Execute the deterministic runtime security pipeline."""
        ...


class AgentRuntimeService:
    _AGENT_ID = "agent-1"
    _WORKSPACE_ROOT = "demo_workspace"

    def __init__(
        self,
        agent: EnterpriseAgent | None = None,
        runtime_service: RuntimeExecutor | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        if agent is None:
            provider = ProviderFactory.create()
            self._agent = OllamaAgent(provider)
        else:
            self._agent = agent

        self._tool_registry = tool_registry or ToolRegistry()

        if tool_registry is None:
            self._register_executable_tools()

        self._runtime_service: RuntimeExecutor

        if runtime_service is not None:
            self._runtime_service = runtime_service
            return

        agent_service = AgentService()
        tool_service = ToolService()
        session_service = SessionService()

        self._register_default_agent(agent_service)

        self._register_default_tools(tool_service)

        authorization_service = AuthorizationService(
            agent_service,
            tool_service,
            PolicyEngine(),
        )

        detection_engine = DetectionEngine(
            [
                PromptInjectionRule(),
            ]
        )

        self._runtime_service = RuntimeService(
            authorization_service,
            session_service,
            detection_engine,
            DetectionService(),
            RiskService(),
            ResponseService(),
        )

    def _register_executable_tools(self) -> None:
        self._tool_registry.register(FileReadTool(self._WORKSPACE_ROOT))

        self._tool_registry.register(DirectoryListTool(self._WORKSPACE_ROOT))

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

        resource = invocation.parameters.get("path")

        session_id = str(uuid.uuid4())

        runtime_result = self._runtime_service.execute(
            session_id=session_id,
            agent_id=self._AGENT_ID,
            tool_id=invocation.tool_id,
            resource=resource,
        )

        decision = runtime_result.event.decision

        response_type = runtime_result.response_action.response_type

        if decision != Decision.ALLOW:
            return AgentRuntimeResult(
                decision=decision.value,
                response_type=response_type,
                output=None,
            )

        tool = self._tool_registry.get(invocation.tool_id)
        output = tool.execute(invocation.parameters)

        return AgentRuntimeResult(
            decision=decision.value,
            response_type=response_type,
            output=output,
        )
