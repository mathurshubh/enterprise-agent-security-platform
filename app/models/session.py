"""Session models and lifecycle state definitions (M4-S)."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TerminalReason(str, Enum):
    """Reason why a session reached terminal state."""

    EXPLICIT_END = "EXPLICIT_END"
    IDLE_TIMEOUT = "IDLE_TIMEOUT"


class TerminalSessionTombstone(BaseModel):
    """Immutable ownership tombstone preserving terminal identity finality (M4-S-1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(min_length=1, description="Unique identifier of the terminal session.")
    agent_id: str = Field(min_length=1, description="Agent that owned the session prior to termination.")
    terminated_at: datetime = Field(description="UTC timestamp when the session reached terminal state.")
    terminal_reason: TerminalReason = Field(description="Authoritative reason for session termination.")


class Session(BaseModel):
    """Represents an active agent interaction session."""

    session_id: str
    agent_id: str
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_activity_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )