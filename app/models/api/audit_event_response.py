from datetime import datetime

from pydantic import BaseModel


class AuditEventResponse(BaseModel):
    """Management API representation of an immutable audit event.

    The timestamp field is a datetime object; FastAPI serialises it to an
    ISO-8601 string automatically.  Manual string conversion is avoided so
    that the serialisation format is governed by Pydantic's json_encoders
    configuration rather than ad-hoc formatting code.
    """

    event_id: str
    agent_id: str
    tool_id: str
    decision: str
    timestamp: datetime
