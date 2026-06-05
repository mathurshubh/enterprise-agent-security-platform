from app.models.agent import Agent, RiskTier


def test_agent_creation():
    agent = Agent(
        agent_id="soc-agent",
        name="SOC Agent",
        owner="Security Operations",
        risk_tier=RiskTier.HIGH,
    )

    assert agent.agent_id == "soc-agent"
    assert agent.risk_tier == RiskTier.HIGH