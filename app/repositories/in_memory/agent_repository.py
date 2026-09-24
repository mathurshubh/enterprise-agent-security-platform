"""InMemoryAgentRepository — In-memory adapter for Agent configuration persistence (ADR-030)."""

from threading import RLock

from app.models.agent import Agent
from app.repositories.interfaces.agent_repository import AgentRepository


class InMemoryAgentRepository(AgentRepository):
    """Thread-safe in-memory repository for Agent configuration.

    Invariants:
    - Object Isolation: Stored and returned entities are defensive deep copies.
    - Missing Records: Non-existent entities return None.
    - Thread-Safe: Synchronized via threading.RLock.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._agents: dict[str, Agent] = {}

    def get(self, agent_id: str) -> Agent | None:
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                return None
            return agent.model_copy(deep=True)

    def save(self, agent: Agent) -> None:
        with self._lock:
            self._agents[agent.agent_id] = agent.model_copy(deep=True)

    def list(self) -> list[Agent]:
        with self._lock:
            return [a.model_copy(deep=True) for a in self._agents.values()]
