import uuid
from typing import Protocol

from app.agents.enterprise_agent import EnterpriseAgent
from app.agents.ollama_agent import OllamaAgent
from app.models.agent_runtime_result import (
    AgentRuntimeResult,
)
from app.models.audit_event import Decision
from app.models.runtime_result import RuntimeResult
from app.providers.provider_factory import ProviderFactory
from app.registry.tool_registry import ToolRegistry
from app.runtime.tool_executor import DefaultToolExecutor
from app.tools.directory_list_tool import DirectoryListTool
from app.tools.file_read_tool import FileReadTool


class AgentIdentityMismatchError(ValueError):
    """Raised when an EnterpriseAgent's claimed agent_id does not match the bound context identity."""


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
    _WORKSPACE_ROOT = "demo_workspace"

    def __init__(
        self,
        agent: EnterpriseAgent | None = None,
        runtime_service: RuntimeExecutor | None = None,
        tool_registry: ToolRegistry | None = None,
        executor: DefaultToolExecutor | None = None,
        agent_id: str | None = None,
    ) -> None:
        if agent is None:
            effective_id = agent_id or "agent-1"
            provider = ProviderFactory.create()
            self._agent = OllamaAgent(provider=provider, agent_id=effective_id)
        else:
            if agent_id is not None and agent.agent_id != agent_id:
                raise AgentIdentityMismatchError(
                    f"Agent identity mismatch: claimed '{agent.agent_id}' does not match expected '{agent_id}'"
                )
            self._agent = agent

        self._tool_registry = tool_registry or ToolRegistry()
        self._executor = executor or DefaultToolExecutor()

        if tool_registry is None:
            self._register_executable_tools()

        self._runtime_service: RuntimeExecutor

        if runtime_service is not None:
            self._runtime_service = runtime_service
            return

        from app.api.dependencies import runtime_service as shared_runtime_service
        self._runtime_service = shared_runtime_service

    @property
    def agent(self) -> EnterpriseAgent:
        return self._agent

    def _register_executable_tools(self) -> None:
        self._tool_registry.register(FileReadTool(self._WORKSPACE_ROOT))

        self._tool_registry.register(DirectoryListTool(self._WORKSPACE_ROOT))

    def execute(
        self,
        query: str,
        agent_id: str | None = None,
    ) -> AgentRuntimeResult:
        if agent_id is not None and self._agent.agent_id != agent_id:
            raise AgentIdentityMismatchError(
                f"Agent identity mismatch: agent claimed '{self._agent.agent_id}' but execution requested '{agent_id}'"
            )

        effective_agent_id = agent_id or self._agent.agent_id

        invocation = self._agent.invoke(query)

        resource = invocation.parameters.get("path")

        session_id = str(uuid.uuid4())

        runtime_result = self._runtime_service.execute(
            session_id=session_id,
            agent_id=effective_agent_id,
            tool_id=invocation.tool_id,
            resource=resource,
            user_prompt=query,
            model_output=invocation.model_dump_json(),
            tool_output="",
        )

        decision = runtime_result.event.decision

        response_type = runtime_result.response_action.response_type

        if decision != Decision.ALLOW:
            return AgentRuntimeResult(
                decision=decision.value,
                response_type=response_type,
                output=None,
            )

        descriptor = self._tool_registry.resolve(invocation.tool_id)
        output = self._executor.execute_descriptor(descriptor, invocation.parameters)

        return AgentRuntimeResult(
            decision=decision.value,
            response_type=response_type,
            output=output,
        )
