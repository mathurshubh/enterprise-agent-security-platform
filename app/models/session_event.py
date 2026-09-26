from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.audit_event import Decision

UNASSIGNED_SEQUENCE: int = 0


class AggregationScope(str, Enum):
    """Scope of behavioral evidence aggregation for detection rules."""

    SESSION = "session"
    AGENT = "agent"


class HorizonQuery(BaseModel):
    """Immutable query specification for selecting eligible detection horizon events."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    scope: AggregationScope
    session_id: str | None = None
    window_seconds: float = Field(gt=0, description="Temporal window size in seconds.")
    evaluation_time: datetime = Field(description="Deterministic evaluation moment.")
    baseline_agent_sequence: int = Field(
        default=0,
        ge=0,
        description="Reinstatement watermark sequence; events at or before this position are excluded.",
    )

    @model_validator(mode="after")
    def validate_scope_parameters(self) -> "HorizonQuery":
        if self.scope == AggregationScope.SESSION:
            if not self.session_id:
                raise ValueError("session_id is required when scope is SESSION")
        elif self.scope == AggregationScope.AGENT:
            if self.session_id is not None:
                raise ValueError("session_id must be None when scope is AGENT")
        return self


class SessionEvent(BaseModel):
    """One recorded step in a session.

    Dual sequencing:
    - ``sequence_number``: Monotonic 1-based position within the session (session-scoped ordering).
    - ``agent_sequence``: Monotonic position within the agent across sessions (agent-scoped ordering and watermark).
      Monotonicity is required; numerical gaplessness is not required.
    Both positions are allocated exclusively by the repository on record.
    """

    session_id: str
    agent_id: str
    tool_id: str
    decision: Decision

    sequence_number: int = Field(
        default=UNASSIGNED_SEQUENCE,
        ge=0,
        description=(
            "Monotonic 1-based position within the session, assigned exclusively "
            "by the repository on record. 0 indicates an unrecorded event."
        ),
    )

    agent_sequence: int = Field(
        default=UNASSIGNED_SEQUENCE,
        ge=0,
        description=(
            "Monotonic position within the agent across sessions, assigned exclusively "
            "by the repository on record. 0 indicates an unrecorded event."
        ),
    )

    final_decision: Decision | None = Field(
        default=None,
        description=(
            "The decision after response enforcement, assigned once when the pipeline "
            "establishes it. None means the request did not reach that point."
        ),
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
