from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Finding(BaseModel):
    finding_id: str
    session_id: str
    agent_id: str
    rule_name: str
    severity: Severity
    description: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
