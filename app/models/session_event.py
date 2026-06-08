from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.models.audit_event import Decision


class SessionEvent(BaseModel):
    session_id: str
    agent_id: str
    tool_id: str
    decision: Decision

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )