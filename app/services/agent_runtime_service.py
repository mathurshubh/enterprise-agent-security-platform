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
from app.models.tool import (
    Tool,
    ToolRiskLevel,
)
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
from app.services.simple_agent import SimpleAgent


class AgentRuntimeService:
    def __init__(self) -> None:
        self._agent = SimpleAgent()

        self._file_read_tool = FileReadTool(
            "demo_workspace"
        )

        self._directory_list_tool = (
            DirectoryListTool(
                "demo_workspace"
            )
        )

        agent_service = AgentService()
        tool_service = ToolService()
        session_service = SessionService()

        agent_service.register_agent(
            Agent(
                agent_id="agent-1",
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

        tool_service.register_tool(
            Tool(
                tool_id="file_read",
                risk_level=ToolRiskLevel.LOW,
                required_permission="files:read",
            )
        )

        tool_service.register_tool(
            Tool(
                tool_id="directory_list",
                risk_level=ToolRiskLevel.LOW,
                required_permission="files:list",
            )
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

    def execute(
        self,
        query: str,
    ) -> AgentRuntimeResult:
        invocation = self._agent.decide_tool(query)

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
                agent_id="agent-1",
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