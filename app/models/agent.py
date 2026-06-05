from enum import Enum

from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"


class RiskTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Agent(BaseModel):
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str
    owner: str
    risk_tier: RiskTier
    approved_tools: list[str] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.REGISTERED