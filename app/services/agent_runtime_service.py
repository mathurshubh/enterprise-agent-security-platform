from app.models.agent_runtime_result import (
    AgentRuntimeResult,
)
from app.models.response_action import (
    ResponseType,
)
from app.services.simple_agent import SimpleAgent


class AgentRuntimeService:
    def __init__(self) -> None:
        self._agent = SimpleAgent()

    def execute(
        self,
        query: str,
    ) -> AgentRuntimeResult:
        invocation = self._agent.decide_tool(query)

        if invocation.tool_id == "file_read":
            return AgentRuntimeResult(
                decision="ALLOW",
                response_type=ResponseType.MONITOR,
                output=(
                    f"Executed file read: "
                    f"{invocation.parameters['path']}"
                ),
            )

        if invocation.tool_id == "directory_list":
            return AgentRuntimeResult(
                decision="ALLOW",
                response_type=ResponseType.MONITOR,
                output=[],
            )

        raise ValueError(
            f"Unsupported tool: "
            f"{invocation.tool_id}"
        )