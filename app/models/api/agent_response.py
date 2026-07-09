from pydantic import BaseModel


class AgentResponse(BaseModel):
    """Management API representation of a registered agent."""

    agent_id: str
    name: str
    owner: str
    risk_tier: str
    status: str
    approved_tools: list[str]
