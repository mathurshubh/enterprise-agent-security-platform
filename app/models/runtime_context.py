"""RuntimeContext — Immutable execution context carrying execution identity only."""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class RuntimeContext(BaseModel):
    """Immutable runtime execution context carrying execution identity only.

    Carries trace identifiers, session identity, user identity, and principal information
    throughout runtime tool execution traversal.

    Authorization decisions are owned by AuthorizationService and RuntimeService and are
    not embedded inside this execution context.
    """

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(description="Unique identifier for the session.")
    request_id: str = Field(description="Unique trace identifier for the request.")
    user_id: str = Field(description="Identifier of the initiating user.")
    principal: str = Field(description="Authenticated principal or service account.")
    authenticated_agent: str = Field(description="Identifier of the authenticated agent.")
    execution_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Immutable execution metadata."
    )


class ToolInvocationContext(BaseModel):
    """Context for a specific tool invocation within a runtime execution."""

    model_config = ConfigDict(frozen=True)

    runtime_context: RuntimeContext = Field(description="Parent runtime context.")
    tool_id: str = Field(description="Target tool identifier.")
    resource: str | None = Field(default=None, description="Target resource identifier.")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Sanitized invocation parameters."
    )
