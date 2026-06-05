from app.models.agent import Agent


class AgentAlreadyExistsError(Exception):
    """Raised when attempting to register an existing agent."""


class AgentNotFoundError(Exception):
    """Raised when an agent cannot be found."""


class AgentService:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register_agent(self, agent: Agent) -> Agent:
        if agent.agent_id in self._agents:
            raise AgentAlreadyExistsError(
                f"Agent '{agent.agent_id}' already exists"
            )

        self._agents[agent.agent_id] = agent
        return agent

    def get_agent(self, agent_id: str) -> Agent:
        if agent_id not in self._agents:
            raise AgentNotFoundError(
                f"Agent '{agent_id}' not found"
            )

        return self._agents[agent_id]

    def list_agents(self) -> list[Agent]:
        return list(self._agents.values())