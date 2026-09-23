from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


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

    The record is **frozen** (ADR-028 property 3: a record is not modified or removed
    after it is written). Enforced by construction rather than by the absence of a
    mutator, because two aliasing paths made the property violable without one:
    ``AuditService.list_events`` returns a shallow copy, so callers received the stored
    objects themselves, and ``record_event`` returns the object it was given, so the
    producer kept a live reference. Neither is a mutator, and both could rewrite
    recorded evidence. A record that can be edited after the fact is not evidence that
    a decision was made; it is a record of what someone last said about it.

    Deriving a changed value stays available through ``model_copy``, which produces a
    new record rather than editing the stored one.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str
    session_id: str
    agent_id: str
    tool_id: str
    decision: Decision
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )