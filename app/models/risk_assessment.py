from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskAssessment(BaseModel):
    session_id: str
    agent_id: str
    risk_score: int
    risk_level: RiskLevel
    finding_count: int
    assessed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
