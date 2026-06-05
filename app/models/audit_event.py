from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class AuditEvent(BaseModel):
    event_id: str
    agent_id: str
    tool: str
    decision: Decision
    timestamp: datetime