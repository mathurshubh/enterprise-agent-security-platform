from app.models.audit_event import Decision
from app.services.agent_service import (
    AgentNotFoundError,
    AgentService,
)
from app.services.tool_service import (
    ToolNotFoundError,
    ToolService,
)
from app.policy.policy_engine import PolicyEngine


class AuthorizationService:
    def __init__(
        self,
        agent_service: AgentService,
        tool_service: ToolService,
        policy_engine: PolicyEngine,
    ) -> None:
        self._agent_service = agent_service
        self._tool_service = tool_service
        self._policy_engine = policy_engine

    def authorize(
        self,
        agent_id: str,
        tool_id: str,
    ) -> Decision:
        try:
            agent = self._agent_service.get_agent(agent_id)
            tool = self._tool_service.get_tool(tool_id)

        except (AgentNotFoundError, ToolNotFoundError):
            return Decision.DENY

        if tool_id not in agent.approved_tools:
            return Decision.DENY

        return self._policy_engine.evaluate(
            agent,
            tool,
        )