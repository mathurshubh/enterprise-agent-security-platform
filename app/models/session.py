from datetime import datetime, timezone
from pydantic import BaseModel, Field


class Session(BaseModel):
    """Represents an agent interaction session."""
    session_id: str
    agent_id: str
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )