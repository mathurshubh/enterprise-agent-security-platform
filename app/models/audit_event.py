from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class AuditEvent(BaseModel):
    """Authoritative record that a security decision was made (ADR-028).

    ``session_id`` is required, not optional. A record that cannot say which
    execution produced the decision is not audit evidence: it establishes that
    something was decided without establishing what it was decided about. Making
    the field optional would allow such a record to be written, and no later
    retention or persistence mechanism could recover the context afterwards —
    retention preserves evidence that was captured; it cannot reconstruct context
    that never was.

    The attribution requirement is semantic (ADR-028 property 2): the record must
    carry sufficient execution context to attribute the decision to its originating
    execution and session. ``session_id`` is the current implementation of that
    requirement, not the requirement itself.
    """

    event_id: str
    session_id: str
    agent_id: str
    tool_id: str
    decision: Decision
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )