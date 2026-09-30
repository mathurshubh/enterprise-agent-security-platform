from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

    Tool identity is recorded as two separate facts, because they answer different
    questions and a single field could not answer either honestly:

    - ``requested_tool_id`` is what crossed the trust boundary. Always present, never
      validated against anything — recording what was asked for is the point, and a
      request naming a tool that does not exist is exactly the case worth auditing.
    - ``tool_id`` and ``tool_version`` are what the security pipeline established. Both
      absent on a request refused at a trust boundary before any resolution occurred;
      ``tool_version`` alone absent where a family resolved but no implementation did.

    Collapsing these would make a record naming ``file_read`` unable to say whether the
    tool existed, resolved, or was merely claimed — which is the distinction an evidence
    record most needs to preserve.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str
    session_id: str
    agent_id: str
    requested_tool_id: str = Field(
        description=(
            "The tool identity the request named, recorded as received. Not constrained: "
            "a malformed or empty value is what some requests carry, and those are the "
            "ones worth auditing."
        ),
    )
    tool_id: str | None = Field(
        default=None,
        description="Resolved tool-family identity, when tool resolution occurred.",
    )
    tool_version: str | None = Field(
        default=None,
        description="Resolved concrete version, when an implementation was established.",
    )
    decision: Decision
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @model_validator(mode="after")
    def _resolved_version_requires_a_resolved_family(self) -> "AuditEvent":
        """A version cannot resolve without the family it belongs to.

        Internal coherence only. That the resolved identity names a *registered* family
        is a repository fact this model has no authority to check, and asserting it here
        would make the model appear to guarantee something it cannot.
        """
        if self.tool_version is not None and self.tool_id is None:
            raise ValueError(
                "tool_version cannot be set without tool_id: a concrete version cannot "
                "resolve without the family it belongs to"
            )
        return self