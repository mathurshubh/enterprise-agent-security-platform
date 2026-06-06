from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class AuditEvent(BaseModel):
    event_id: str
    agent_id: str
    tool_id: str
    decision: Decision
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )