from app.models.agent_runtime_result import (
    AgentRuntimeResult,
)
from app.models.response_action import (
    ResponseType,
)
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

    def execute(
        self,
        query: str,
    ) -> AgentRuntimeResult:
        invocation = self._agent.decide_tool(query)

        if invocation.tool_id == "file_read":
            output = self._file_read_tool.read(
                invocation.parameters[
                    "path"
                ]
            )

            return AgentRuntimeResult(
                decision="ALLOW",
                response_type=(
                    ResponseType.MONITOR
                ),
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
                decision="ALLOW",
                response_type=(
                    ResponseType.MONITOR
                ),
                output=output,
            )

        raise ValueError(
            f"Unsupported tool: "
            f"{invocation.tool_id}"
        )