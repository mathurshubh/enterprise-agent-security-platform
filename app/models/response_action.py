from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from app.models.risk_assessment import RiskLevel


class ResponseType(str, Enum):
    MONITOR = "MONITOR"
    ALERT = "ALERT"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    SUSPEND_AGENT = "SUSPEND_AGENT"


class ResponseAction(BaseModel):
    session_id: str
    agent_id: str
    risk_level: RiskLevel
    response_type: ResponseType
    reason: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
