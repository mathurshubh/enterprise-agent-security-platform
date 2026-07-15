from datetime import datetime

from pydantic import BaseModel


class SessionResponse(BaseModel):
    """Management API representation of an active session.

    Maps directly to the underlying Session domain model.
    """

    session_id: str
    agent_id: str
    started_at: datetime
