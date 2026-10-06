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
    """An agent's identity and descriptive configuration.

    ``status`` is **not** part of that configuration and is **not persisted**. It is a
    computed projection over the administrative and enforcement planes, filled in by
    ``AgentService`` on read (ADR-030 AP.1), and it must never be consumed by a security
    decision: authorization evaluates each plane independently against its own authority
    (ADR-024 A.4), which a single collapsed value cannot express.

    A record read straight from the repository therefore carries the default below rather
    than a lifecycle fact. That default is ``REGISTERED``, which is non-executable, so a
    caller that bypasses the service and reads the raw record fails closed rather than
    obtaining an executable agent.
    """

    agent_id: str = Field(..., description="Unique agent identifier")
    name: str
    owner: str
    risk_tier: RiskTier
    approved_tools: list[str] = Field(default_factory=list)
    status: AgentStatus = Field(
        default=AgentStatus.REGISTERED,
        description=(
            "Computed lifecycle projection. Never persisted, never an authorization "
            "input. Non-executable by default so a raw repository read fails closed."
        ),
    )