from pydantic import BaseModel

from app.models.finding import Finding
from app.models.session_event import SessionEvent


class RuntimeResult(BaseModel):
    event: SessionEvent
    findings: list[Finding]
