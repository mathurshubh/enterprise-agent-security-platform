"""ExecutionCapability domain models — frozen specifications of sandbox capabilities (ADR-032)."""

import hashlib
import json
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

BLOCKED_ENVIRONMENT_KEYS: frozenset[str] = frozenset(
    {
        "POSTGRES_URL",
        "POSTGRES_PASSWORD",
        "POSTGRES_USER",
        "POSTGRES_DB",
        "DATABASE_URL",
        "JWT_SECRET_KEY",
        "SECRET_KEY",
        "API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AZURE_CLIENT_SECRET",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    }
)


class FilesystemCapability(BaseModel):
    """Specification of filesystem boundaries for sandbox execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    workspace_root: str = Field(min_length=1)
    read_only: bool = True
    allowed_subpaths: tuple[str, ...] = Field(default_factory=tuple)
    allow_temp_writes: bool = False

    @field_validator("workspace_root", mode="after")
    @classmethod
    def _validate_workspace_root(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("workspace_root must not contain null bytes")
        path = Path(v)
        if not path.is_absolute():
            raise ValueError(f"workspace_root must be an absolute path: '{v}'")
        resolved = str(path.resolve())
        return resolved

    @field_validator("allowed_subpaths", mode="before")
    @classmethod
    def _normalize_allowed_subpaths(cls, v: Any) -> tuple[str, ...]:
        if isinstance(v, (list, tuple, set, frozenset)):
            normalized = []
            for item in v:
                if not isinstance(item, str):
                    raise ValueError(f"Subpath item must be a string, got: {type(item)}")
                if "\x00" in item:
                    raise ValueError("Subpath must not contain null bytes")
                if item.startswith("/"):
                    raise ValueError(f"allowed_subpath must be relative to workspace_root: '{item}'")
                p = Path(item)
                if any(part == ".." for part in p.parts):
                    raise ValueError(f"allowed_subpath must not contain traversal elements: '{item}'")
                normalized.append(item.strip("/"))
            return tuple(normalized)
        raise ValueError(f"allowed_subpaths must be a sequence, got {type(v)}")


class NetworkEgressMode(str, Enum):
    """Modes for network egress isolation."""

    DISABLED = "disabled"
    ALLOWLIST = "allowlist"


class NetworkDestination(BaseModel):
    """Structured specification of an allowed network destination."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)

    @field_validator("host", mode="after")
    @classmethod
    def _validate_host(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not cleaned:
            raise ValueError("Host cannot be empty")
        if "\x00" in cleaned or " " in cleaned:
            raise ValueError(f"Host contains invalid characters: '{cleaned}'")
        return cleaned

    def to_string(self) -> str:
        return f"{self.host}:{self.port}"


class NetworkCapability(BaseModel):
    """Specification of network boundaries for sandbox execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: NetworkEgressMode = NetworkEgressMode.DISABLED
    destinations: tuple[NetworkDestination, ...] = Field(default_factory=tuple)
    allowed_destinations: tuple[str, ...] = Field(default_factory=tuple)
    allow_unix_sockets: bool = False
    allow_bind: bool = False

    @field_validator("destinations", mode="before")
    @classmethod
    def _normalize_destinations_objs(cls, v: Any) -> tuple[NetworkDestination, ...]:
        if isinstance(v, (list, tuple, set, frozenset)):
            result = []
            for item in v:
                if isinstance(item, NetworkDestination):
                    result.append(item)
                elif isinstance(item, dict):
                    result.append(NetworkDestination(**item))
                elif isinstance(item, str):
                    cleaned = item.strip()
                    parts = cleaned.split(":")
                    if len(parts) != 2:
                        raise ValueError(f"Destination must be 'host:port', got: '{cleaned}'")
                    result.append(NetworkDestination(host=parts[0], port=int(parts[1])))
                else:
                    raise ValueError(f"Invalid destination object: {item}")
            return tuple(result)
        raise ValueError(f"destinations must be a sequence, got {type(v)}")

    @field_validator("allowed_destinations", mode="before")
    @classmethod
    def _normalize_destinations_str(cls, v: Any) -> tuple[str, ...]:
        if isinstance(v, (list, tuple, set, frozenset)):
            normalized = []
            for item in v:
                if isinstance(item, NetworkDestination):
                    normalized.append(item.to_string())
                    continue
                if not isinstance(item, str):
                    raise ValueError(f"Destination must be a string: {item}")
                cleaned = item.strip().lower()
                if not cleaned:
                    raise ValueError("Destination cannot be empty")
                if "\x00" in cleaned or " " in cleaned:
                    raise ValueError(f"Destination contains invalid characters: '{cleaned}'")
                parts = cleaned.split(":")
                if len(parts) != 2:
                    raise ValueError(
                        f"Destination must be in 'host:port' format, got: '{cleaned}'"
                    )
                host, port_str = parts
                if not host:
                    raise ValueError(f"Destination host cannot be empty: '{cleaned}'")
                try:
                    port = int(port_str)
                    if not (1 <= port <= 65535):
                        raise ValueError()
                except ValueError:
                    raise ValueError(
                        f"Destination port must be integer between 1 and 65535: '{port_str}'"
                    ) from None
                normalized.append(f"{host}:{port}")
            return tuple(normalized)
        raise ValueError(f"allowed_destinations must be a sequence, got {type(v)}")

    @field_validator("allowed_destinations", mode="after")
    @classmethod
    def _sync_and_validate_destinations(
        cls, allowed_destinations: tuple[str, ...], info: Any
    ) -> tuple[str, ...]:
        data = info.data
        mode = data.get("mode", NetworkEgressMode.DISABLED)
        destinations = data.get("destinations", ())

        # Reconcile destinations and allowed_destinations
        all_dests = set(allowed_destinations)
        for d in destinations:
            all_dests.add(d.to_string())

        if mode == NetworkEgressMode.DISABLED and len(all_dests) > 0:
            raise ValueError(
                "allowed_destinations must be empty when network egress mode is DISABLED"
            )
        if mode == NetworkEgressMode.ALLOWLIST and len(all_dests) == 0:
            raise ValueError(
                "allowed_destinations must contain at least one destination when mode is ALLOWLIST"
            )
        return tuple(sorted(all_dests))

    def model_post_init(self, context: Any, /) -> None:
        # Ensure destinations and allowed_destinations are synchronized
        if self.allowed_destinations and not self.destinations:
            objs = []
            for item in self.allowed_destinations:
                h, p = item.split(":")
                objs.append(NetworkDestination(host=h, port=int(p)))
            object.__setattr__(self, "destinations", tuple(objs))
        elif self.destinations and not self.allowed_destinations:
            object.__setattr__(
                self,
                "allowed_destinations",
                tuple(d.to_string() for d in self.destinations),
            )


class ResourceLimits(BaseModel):
    """Resource constraints for sandboxed tool execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_memory_bytes: int = Field(default=256 * 1024 * 1024, gt=0, le=4 * 1024 * 1024 * 1024)
    max_cpu_seconds: float = Field(default=5.0, gt=0.0, le=300.0)
    max_output_bytes: int = Field(default=1024 * 1024, ge=0, le=100 * 1024 * 1024)
    wall_clock_timeout_seconds: float = Field(default=10.0, gt=0.0, le=600.0)
    required_controls: tuple[str, ...] = Field(
        default=(),
        description=(
            "Controls this profile requires the sandbox to establish before the "
            "workload starts. A required control that cannot be established refuses "
            "the launch. The profile owns what execution requires; the sandbox "
            "implementation owns what it can enforce. Empty means no control is "
            "mandatory — but a control that is attempted and fails still refuses, "
            "because optional means the platform may operate without it, not that "
            "failures while establishing it may be ignored."
        ),
    )

    @field_validator("required_controls", mode="after")
    @classmethod
    def _validate_required_controls(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        known = {"memory", "cpu"}
        unknown = sorted(set(v) - known)
        if unknown:
            raise ValueError(
                f"unknown required control(s): {unknown}; known controls are {sorted(known)}"
            )
        return tuple(sorted(set(v)))


class ExecutionCapabilities(BaseModel):
    """Frozen capability specification governing sandbox execution of an authorized tool."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    capability_profile_id: str = Field(min_length=1)
    filesystem: FilesystemCapability
    environment_variables: Mapping[str, str] = Field(default_factory=dict)
    network: NetworkCapability = Field(default_factory=NetworkCapability)
    resources: ResourceLimits = Field(default_factory=ResourceLimits)

    @field_validator("environment_variables", mode="after")
    @classmethod
    def _validate_environment(cls, v: Any) -> Mapping[str, str]:
        if not isinstance(v, Mapping):
            raise ValueError(f"environment_variables must be a mapping, got: {type(v)}")
        frozen_env = {}
        for k, val in v.items():
            if not isinstance(k, str) or not isinstance(val, str):
                raise ValueError(
                    f"Environment keys and values must be strings, got: ({type(k)}, {type(val)})"
                )
            key_upper = k.upper().strip()
            if key_upper in BLOCKED_ENVIRONMENT_KEYS or any(
                blocked in key_upper for blocked in ("SECRET", "PASSWORD", "POSTGRES_URL")
            ):
                raise ValueError(
                    f"Platform secret or dangerous key '{k}' cannot be in sandbox environment allowlist"
                )
            if "\x00" in k or "\x00" in val:
                raise ValueError("Environment keys and values must not contain null bytes")
            frozen_env[k] = val
        return MappingProxyType(frozen_env)

    def compute_digest(self) -> str:
        """Compute deterministic SHA-256 digest of the effective capability set.

        The digest is computed from canonical JSON representation where all
        semantically unordered collections (destinations, subpaths, env vars)
        are explicitly sorted.
        """
        canonical_dict = {
            "capability_profile_id": self.capability_profile_id,
            "filesystem": {
                "workspace_root": self.filesystem.workspace_root,
                "read_only": self.filesystem.read_only,
                "allowed_subpaths": sorted(set(self.filesystem.allowed_subpaths)),
                "allow_temp_writes": self.filesystem.allow_temp_writes,
            },
            "environment_variables": sorted(
                [(k, v) for k, v in self.environment_variables.items()],
                key=lambda x: x[0],
            ),
            "network": {
                "allow_bind": self.network.allow_bind,
                "allow_unix_sockets": self.network.allow_unix_sockets,
                "allowed_destinations": sorted(set(self.network.allowed_destinations)),
                "mode": self.network.mode.value,
            },
            "resources": {
                "max_memory_bytes": self.resources.max_memory_bytes,
                "max_cpu_seconds": self.resources.max_cpu_seconds,
                "max_output_bytes": self.resources.max_output_bytes,
                "wall_clock_timeout_seconds": self.resources.wall_clock_timeout_seconds,
            },
        }
        canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
