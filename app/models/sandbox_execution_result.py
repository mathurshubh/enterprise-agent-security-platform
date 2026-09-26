"""SandboxExecutionResult domain model — structured outcome of sandboxed tool execution (ADR-032)."""

from types import MappingProxyType
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SandboxExecutionResult(BaseModel):
    """Structured, immutable outcome returned by a ToolExecutionSandbox."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    success: bool
    output: Any | None = None
    output_digest: str | None = None
    exit_code: int = 0
    duration_ms: int = Field(default=0, ge=0)
    error_type: str | None = None
    error_message: str | None = None
    resource_usage: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("resource_usage", mode="after")
    @classmethod
    def _freeze_resource_usage(cls, v: Any) -> Mapping[str, Any]:
        if isinstance(v, Mapping):
            return MappingProxyType(dict(v))
        raise ValueError(f"resource_usage must be a mapping, got {type(v)}")
