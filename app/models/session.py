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

    session_id: str = Field(
        min_length=1, description="Unique identifier of the terminal session."
    )
    agent_id: str = Field(
        min_length=1, description="Agent that owned the session prior to termination."
    )
    terminated_at: datetime = Field(
        description="UTC timestamp when the session reached terminal state."
    )
    terminal_reason: TerminalReason = Field(
        description="Authoritative reason for session termination."
    )


class Session(BaseModel):
    """Represents an active agent interaction session."""

    session_id: str
    agent_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class SessionAlreadyExistsError(Exception):
    """Raised when attempting to create a session that already exists."""


class SessionNotFoundError(Exception):
    """Raised when an operation references a session that does not exist."""


class SessionBindingError(Exception):
    """Raised when a session is used by an agent that does not own it.

    A session is security-owned by exactly one agent. Evidence gathered in a session
    feeds that agent's enforcement posture (M2b), so allowing another agent to write
    into it would let one workload manipulate another workload's security state.
    """

    def __init__(
        self, session_id: str, owner_agent_id: str, requested_agent_id: str
    ) -> None:
        super().__init__(
            f"Session '{session_id}' is owned by agent '{owner_agent_id}', "
            f"not '{requested_agent_id}'"
        )
        self.session_id = session_id
        self.owner_agent_id = owner_agent_id
        self.requested_agent_id = requested_agent_id


class SessionTerminalError(SessionBindingError):
    """Raised when an operation attempts to use or rebind a terminal session (M4-S-1).

    Subclasses SessionBindingError so that existing security boundaries (such as
    RuntimeService and HTTP API handlers) catch it and fail closed with
    SESSION_BINDING_INVALID without leaking state or requiring broad refactoring.
    """

    def __init__(
        self, session_id: str, owner_agent_id: str, requested_agent_id: str
    ) -> None:
        super().__init__(
            session_id=session_id,
            owner_agent_id=owner_agent_id,
            requested_agent_id=requested_agent_id,
        )


class SessionRepositoryError(Exception):
    """Base exception for session repository persistence and infrastructure failures."""


class HorizonUnavailableError(SessionRepositoryError):
    """Raised when the authoritative behavioral detection horizon is unavailable (fail closed)."""
