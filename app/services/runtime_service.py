from app.auth.authorization_service import AuthorizationService
from app.detection.context import DetectionContext
from app.detection.engine import DetectionEngine
from app.detection.prompt_injection_rule import PromptInjectionRule
from app.detection.sensitive_file_access_rule import SensitiveFileAccessRule
from app.detection.data_exfiltration_rule import DataExfiltrationRule
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.runtime_result import RuntimeResult
from app.models.risk_assessment import (
    RiskAssessment,
    RiskLevel,
)
from app.models.session_event import SessionEvent
from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.policy.policy_engine import PolicyEngine
from app.services.agent_service import AgentService
from app.services.detection_service import DetectionService
from app.services.response_service import ResponseService
from app.models.audit_event import Decision
from app.models.response_action import ResponseType
from app.services.risk_service import RiskService
from app.services.session_service import SessionService
from app.services.tool_service import ToolService


class RuntimeService:
    def __init__(
        self,
        authorization_service: AuthorizationService,
        session_service: SessionService,
        detection_engine: DetectionEngine,
        detection_service: DetectionService,
        risk_service: RiskService,
        response_service: ResponseService,
    ) -> None:
        self._authorization_service = authorization_service
        self._session_service = session_service
        self._detection_engine = detection_engine
        self._detection_service = detection_service
        self._risk_service = risk_service
        self._response_service = response_service

    @classmethod
    def create_default(
        cls,
        agent_id: str = "agent-1",
    ) -> "RuntimeService":
        agent_service = AgentService()
        tool_service = ToolService()
        session_service = SessionService()

        cls._register_default_agent(
            agent_service,
            agent_id,
        )
        cls._register_default_tools(tool_service)

        authorization_service = AuthorizationService(
            agent_service,
            tool_service,
            PolicyEngine(),
        )
        detection_engine = DetectionEngine(
            [
                PromptInjectionRule(),
                SensitiveFileAccessRule(),
                DataExfiltrationRule(),
            ]
        )

        return cls(
            authorization_service,
            session_service,
            detection_engine,
            DetectionService(),
            RiskService(),
            ResponseService(),
        )

    @staticmethod
    def _register_default_agent(
        agent_service: AgentService,
        agent_id: str,
    ) -> None:
        agent_service.register_agent(
            Agent(
                agent_id=agent_id,
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
        session_id: str,
        agent_id: str,
        tool_id: str,
        resource: str | None = None,
        user_prompt: str = "",
        model_output: str = "",
        tool_output: str = "",
    ) -> RuntimeResult:
        decision = self._authorization_service.authorize(
            agent_id,
            tool_id,
            resource,
        )

        event = SessionEvent(
            session_id=session_id,
            agent_id=agent_id,
            tool_id=tool_id,
            decision=decision,
        )

        recorded_event = self._session_service.record_event(event)
        session_events = self._session_service.list_events(session_id)

        content_findings = self._detection_engine.evaluate(
            DetectionContext(
                session_id=session_id,
                agent_id=agent_id,
                user_prompt=user_prompt,
                model_output=model_output,
                tool_output=tool_output,
                metadata={
                    "tool_id": tool_id,
                    "resource": resource or "",
                },
            )
        )
        session_findings = self._detection_service.detect_excessive_denials(
            session_events
        )
        findings = content_findings + session_findings

        if findings:
            risk_assessment = self._risk_service.assess(findings)
        else:
            risk_assessment = RiskAssessment(
                session_id=session_id,
                agent_id=agent_id,
                risk_score=0,
                risk_level=RiskLevel.LOW,
                finding_count=0,
            )

        response_action = (
            self._response_service.recommend(
                risk_assessment
            )
        )

        # Enforce Zero Trust response actions on final decision
        if recorded_event.decision == Decision.ALLOW:
            if response_action.response_type == ResponseType.SUSPEND_AGENT:
                recorded_event.decision = Decision.DENY
            elif response_action.response_type == ResponseType.REQUIRE_APPROVAL:
                recorded_event.decision = Decision.APPROVAL_REQUIRED

        return RuntimeResult(
            event=recorded_event,
            findings=findings,
            risk_assessment=risk_assessment,
            response_action=response_action,
        )

