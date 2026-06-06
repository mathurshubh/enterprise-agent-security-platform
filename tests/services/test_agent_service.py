import pytest
from app.models.agent import (
    Agent,
    AgentStatus,
    RiskTier,
)
from app.services.agent_service import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    AgentService,
)


def create_agent(agent_id: str = "soc-agent") -> Agent:
    return Agent(
        agent_id=agent_id,
        name="SOC Agent",
        owner="security-team",
        risk_tier=RiskTier.HIGH,
        approved_tools=["file_read"],
        status=AgentStatus.ACTIVE,
    )


def test_register_agent():
    service = AgentService()

    agent = create_agent()

    service.register_agent(agent)

    assert service.get_agent("soc-agent") == agent


def test_duplicate_agent_rejected():
    service = AgentService()

    agent = create_agent()

    service.register_agent(agent)

    with pytest.raises(AgentAlreadyExistsError):
        service.register_agent(agent)


def test_get_unknown_agent():
    service = AgentService()

    with pytest.raises(AgentNotFoundError):
        service.get_agent("missing-agent")


def test_list_agents():
    service = AgentService()

    service.register_agent(create_agent("agent-1"))
    service.register_agent(create_agent("agent-2"))

    agents = service.list_agents()

    assert len(agents) == 2