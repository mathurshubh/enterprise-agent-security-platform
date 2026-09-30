"""ToolExecutionDescriptor — Typed JSON-serializable execution payload (ADR-032)."""

import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolExecutionDescriptor(BaseModel):
    """Typed execution descriptor passed from parent security process to child runner.

    Invariants (ADR-032):
    1. No arbitrary Python objects: Only serializable descriptors, tool_id, implementation_id,
       and parameters cross the process boundary.
    2. Deeply frozen: Parameters are frozen to MappingProxyType.
    3. Strict JSON compatibility: Pure JSON serializable.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    tool_id: str = Field(min_length=1)
    tool_version: str | None = Field(
        default=None,
        description=(
            "Concrete version this execution is attributable to. Identity and provenance "
            "only: the child selects an implementation by implementation_id and must "
            "never derive one from tool_id and version, which would rebuild the inference "
            "this field exists to replace."
        ),
    )
    implementation_id: str = Field(min_length=1)
    parameters: Mapping[str, Any] = Field(default_factory=dict)
    grant_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    request_id: str | None = None
    filesystem: Mapping[str, Any] | None = None
    scratch_dir: str | None = None
    network: Mapping[str, Any] | None = None

    @field_validator("parameters", mode="after")
    @classmethod
    def _freeze_parameters(cls, v: Any) -> Mapping[str, Any]:
        if isinstance(v, Mapping):
            return MappingProxyType(dict(v))
        raise ValueError(f"parameters must be a mapping, got: {type(v)}")

    @field_validator("filesystem", mode="after")
    @classmethod
    def _freeze_filesystem(cls, v: Any) -> Mapping[str, Any] | None:
        if v is None:
            return None
        if isinstance(v, Mapping):
            return MappingProxyType(dict(v))
        raise ValueError(f"filesystem must be a mapping, got: {type(v)}")

    @field_validator("network", mode="after")
    @classmethod
    def _freeze_network(cls, v: Any) -> Mapping[str, Any] | None:
        if v is None:
            return None
        if isinstance(v, Mapping):
            return MappingProxyType(dict(v))
        raise ValueError(f"network must be a mapping, got: {type(v)}")

    def to_json(self) -> str:
        """Serialize descriptor to canonical JSON string."""
        data = {
            "tool_id": self.tool_id,
            "tool_version": self.tool_version,
            "implementation_id": self.implementation_id,
            "parameters": dict(self.parameters),
            "grant_id": self.grant_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "request_id": self.request_id,
            "filesystem": dict(self.filesystem) if self.filesystem is not None else None,
            "scratch_dir": self.scratch_dir,
            "network": dict(self.network) if self.network is not None else None,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, json_str: str) -> "ToolExecutionDescriptor":
        """Deserialize descriptor from JSON string."""
        raw = json.loads(json_str)
        return cls(
            tool_id=raw["tool_id"],
            tool_version=raw.get("tool_version"),
            implementation_id=raw["implementation_id"],
            parameters=raw.get("parameters", {}),
            grant_id=raw.get("grant_id"),
            session_id=raw.get("session_id"),
            agent_id=raw.get("agent_id"),
            request_id=raw.get("request_id"),
            filesystem=raw.get("filesystem"),
            scratch_dir=raw.get("scratch_dir"),
            network=raw.get("network"),
        )
