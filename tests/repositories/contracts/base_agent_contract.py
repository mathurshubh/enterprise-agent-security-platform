"""Reusable contract tests for AgentRepository implementations."""

import abc

from app.models.agent import Agent, AgentStatus, RiskTier
from app.repositories.interfaces.agent_repository import AgentRepository


class BaseAgentRepositoryContractTests(abc.ABC):
    """Abstract contract test suite for any AgentRepository adapter."""

    @abc.abstractmethod
    def create_repository(self) -> AgentRepository:
        """Factory method to construct a fresh, empty repository under test."""
        raise NotImplementedError

    def _sample_agent(self, agent_id: str = "agent-1", name: str = "Agent 1") -> Agent:
        return Agent(
            agent_id=agent_id,
            name=name,
            owner="sec-ops",
            status=AgentStatus.ACTIVE,
            risk_tier=RiskTier.LOW,
            approved_tools=["filesystem", "network"],
        )

    def test_save_and_get_entity(self) -> None:
        repo = self.create_repository()
        agent = self._sample_agent()

        repo.save(agent)
        retrieved = repo.get(agent.agent_id)

        assert retrieved is not None
        assert retrieved.agent_id == agent.agent_id
        assert retrieved.name == agent.name
        assert retrieved.status == agent.status
        assert retrieved.risk_tier == agent.risk_tier
        assert retrieved.approved_tools == agent.approved_tools

    def test_get_missing_entity_returns_none(self) -> None:
        repo = self.create_repository()
        assert repo.get("non-existent-agent") is None

    def test_list_entities_empty_and_populated(self) -> None:
        repo = self.create_repository()
        assert repo.list() == []

        a1 = self._sample_agent("agent-1", "Agent 1")
        a2 = self._sample_agent("agent-2", "Agent 2")

        repo.save(a1)
        repo.save(a2)

        agents = repo.list()
        assert len(agents) == 2
        agent_ids = {a.agent_id for a in agents}
        assert agent_ids == {"agent-1", "agent-2"}

    def test_save_defensive_copy_isolation(self) -> None:
        """Mutating the source object after save must not affect repository state."""
        repo = self.create_repository()
        agent = self._sample_agent("agent-iso-1")
        repo.save(agent)

        # Mutate local object
        agent.approved_tools.append("tampered")

        # Repository state must remain unmutated
        retrieved = repo.get("agent-iso-1")
        assert retrieved is not None
        assert "tampered" not in retrieved.approved_tools

    def test_get_defensive_copy_isolation(self) -> None:
        """Mutating a retrieved object must not affect repository state."""
        repo = self.create_repository()
        agent = self._sample_agent("agent-iso-2")
        repo.save(agent)

        retrieved1 = repo.get("agent-iso-2")
        assert retrieved1 is not None
        retrieved1.approved_tools.append("tampered")

        retrieved2 = repo.get("agent-iso-2")
        assert retrieved2 is not None
        assert "tampered" not in retrieved2.approved_tools

    def test_list_collection_isolation(self) -> None:
        """Mutating the list returned by list() must not affect subsequent queries."""
        repo = self.create_repository()
        agent = self._sample_agent("agent-iso-3")
        repo.save(agent)

        agent_list = repo.list()
        agent_list.clear()

        assert len(repo.list()) == 1
