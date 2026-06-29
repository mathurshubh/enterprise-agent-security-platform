import pytest

from app.models.audit_event import Decision
from app.models.agent_runtime_result import (
    AgentRuntimeResult,
)
from app.models.response_action import (
    ResponseAction,
    ResponseType,
)
from app.models.risk_assessment import (
    RiskAssessment,
    RiskLevel,
)
from app.models.runtime_result import RuntimeResult
from app.models.session_event import SessionEvent
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_invocation import (
    ToolInvocation,
)
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.registry.tool_registry import (
    ToolNotRegisteredError,
    ToolRegistry,
)
from app.services.agent_runtime_service import (
    AgentRuntimeService,
)
from app.tools.base_tool import BaseTool


class FakeAgent:
    def invoke(
        self,
        query: str,
    ) -> ToolInvocation:
        normalized_query = query.strip().lower()

        if normalized_query.startswith("read "):
            return ToolInvocation(
                tool_id="file_read",
                parameters={
                    "path": query.strip()[5:],
                },
            )

        if normalized_query == "list files":
            return ToolInvocation(
                tool_id="directory_list",
                parameters={
                    "path": ".",
                },
            )

        return ToolInvocation(
            tool_id="",
            parameters={},
        )


class UnknownToolAgent:
    def invoke(
        self,
        query: str,
    ) -> ToolInvocation:
        return ToolInvocation(
            tool_id="unregistered_tool",
            parameters={
                "path": ".",
            },
        )


class AllowingRuntimeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, str | None]] = []

    def execute(
        self,
        session_id: str,
        agent_id: str,
        tool_id: str,
        resource: str | None = None,
    ) -> RuntimeResult:
        self.calls.append(
            {
                "session_id": session_id,
                "agent_id": agent_id,
                "tool_id": tool_id,
                "resource": resource,
            }
        )

        return RuntimeResult(
            event=SessionEvent(
                session_id=session_id,
                agent_id=agent_id,
                tool_id=tool_id,
                decision=Decision.ALLOW,
            ),
            findings=[],
            risk_assessment=RiskAssessment(
                session_id=session_id,
                agent_id=agent_id,
                risk_score=0,
                risk_level=RiskLevel.LOW,
                finding_count=0,
            ),
            response_action=ResponseAction(
                session_id=session_id,
                agent_id=agent_id,
                risk_level=RiskLevel.LOW,
                response_type=ResponseType.MONITOR,
                reason="allowed for test",
            ),
        )


class RecordingTool(BaseTool):
    def __init__(
        self,
        tool_id: str,
        output: str,
    ) -> None:
        self._metadata = ToolMetadata(
            identity=ToolIdentity(
                tool_id=tool_id,
                name="Recording Tool",
                description="Records execution parameters",
            ),
            governance=ToolGovernance(
                risk_level=ToolRiskLevel.LOW,
                required_permissions=[],
            ),
            capability=ToolCapability(
                category="test",
            ),
            operational=ToolOperational(),
        )
        self.output = output
        self.parameters: dict[str, object] | None = None

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def execute(
        self,
        parameters: dict[str, object],
    ) -> str:
        self.parameters = parameters
        return self.output


def create_service() -> AgentRuntimeService:
    return AgentRuntimeService(
        agent=FakeAgent(),
    )


def test_execute_read_query() -> None:
    service = create_service()

    result = service.execute(
        "read notes.txt"
    )

    assert isinstance(
        result,
        AgentRuntimeResult,
    )

    assert result.decision == "ALLOW"

    assert (
        result.response_type
        == ResponseType.MONITOR
    )

    assert isinstance(
        result.output,
        str,
    )


def test_execute_protected_resource_query() -> None:
    service = create_service()

    result = service.execute(
        "read secrets.txt"
    )

    assert isinstance(
        result,
        AgentRuntimeResult,
    )

    assert result.decision == "DENY"

    assert result.output is None


def test_execute_list_query() -> None:
    service = create_service()

    result = service.execute(
        "list files"
    )

    assert isinstance(
        result,
        AgentRuntimeResult,
    )

    assert result.decision == "ALLOW"

    assert (
        result.response_type
        == ResponseType.MONITOR
    )

    assert isinstance(
        result.output,
        list,
    )

    assert all(
        isinstance(item, str)
        for item in result.output
    )


def test_execute_uses_tool_registry_for_approved_tool() -> None:
    service = create_service()
    registry = ToolRegistry()
    tool = RecordingTool(
        "file_read",
        "registry output",
    )
    registry.register(tool)
    runtime_service = AllowingRuntimeService()

    service._tool_registry = registry
    service._runtime_service = runtime_service

    result = service.execute(
        "read notes.txt"
    )

    assert result.decision == "ALLOW"
    assert (
        result.response_type
        == ResponseType.MONITOR
    )
    assert result.output == "registry output"
    assert tool.parameters == {
        "path": "notes.txt",
    }
    assert runtime_service.calls[0]["tool_id"] == "file_read"


def test_execute_allowed_unregistered_tool_raises_error() -> None:
    service = AgentRuntimeService(
        agent=UnknownToolAgent(),
    )
    service._runtime_service = AllowingRuntimeService()

    with pytest.raises(
        ToolNotRegisteredError,
        match="unregistered_tool",
    ):
        service.execute("use unknown tool")



def test_execute_unsupported_query() -> None:
    service = create_service()

    result = service.execute(
        "send email"
    )

    assert isinstance(
        result,
        AgentRuntimeResult,
    )

    assert result.decision == "DENY"

    assert (
        result.response_type
        == ResponseType.MONITOR
    )

    assert result.output is None
