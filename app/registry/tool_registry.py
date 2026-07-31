"""Authoritative Tool Registry managing tool registration, resolution, versioning, and lifecycle descriptors."""

from collections.abc import Callable
import threading
from typing import Any

from app.models.tool_descriptor import ToolDescriptor
from app.models.tool_metadata import ToolMetadata
from app.runtime.tool_executor import DefaultToolExecutor
from app.tools.base_tool import BaseTool


class DuplicateToolRegistrationError(Exception):
    """Raised when a tool or tool_id with the same version is already registered."""


class ToolNotRegisteredError(Exception):
    """Raised when a tool is not registered in the registry."""


class ToolMetadataValidationError(Exception):
    """Raised when tool metadata is invalid or missing required fields."""


class ToolVersionMismatchError(Exception):
    """Raised when the requested tool version does not match any registered version."""


class ToolRegistry:
    """Single authoritative Tool Registry for executable platform tools and metadata descriptors.

    Manages tool registration, descriptor resolution (`resolve`), metadata discovery,
    isolated version matching (`_match_version`), and factory registration.
    All operations are thread-safe (`threading.RLock`).

    Internal Storage Architecture:
        Tools are stored internally in a two-level dictionary: `_descriptors[tool_id][version] -> ToolDescriptor`.
        This isolates version comparison logic and prepares the registry for seamless future multi-version
        loading without breaking existing single-version resolution behavior.

    Tool Execution Separation:
        The ToolRegistry resolves passive `ToolDescriptor` objects. Tool instantiation and execution
        are handled by `DefaultToolExecutor`.

    Explicitly isolated from security decision-making (authorization, policy evaluation,
    risk scoring, detection, enforcement).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Storage structure: tool_id -> {version: ToolDescriptor}
        self._descriptors: dict[str, dict[str, ToolDescriptor]] = {}
        self._executor = DefaultToolExecutor()

    def register(self, tool: BaseTool) -> BaseTool:
        """Register an executable BaseTool instance.

        Validates tool identity metadata, creates a ToolDescriptor, and stores it under
        tool_id and version.

        Raises:
            ToolMetadataValidationError: If tool_id or name is missing/empty.
            DuplicateToolRegistrationError: If tool_id with the same version is already registered.
        """
        self._validate_tool_metadata(tool)

        descriptor = ToolDescriptor(
            metadata=tool.metadata,
            instance=tool,
            tool_class=type(tool),
            enabled=True,
            registration_state="REGISTERED",
        )

        with self._lock:
            tool_id = descriptor.tool_id
            version = descriptor.version

            if tool_id not in self._descriptors:
                self._descriptors[tool_id] = {}

            if version in self._descriptors[tool_id]:
                raise DuplicateToolRegistrationError(
                    f"Tool '{tool_id}' version '{version}' is already registered"
                )

            self._descriptors[tool_id][version] = descriptor
            return tool

    def register_factory(
        self,
        tool_id: str,
        factory: Callable[..., BaseTool],
        metadata: ToolMetadata | None = None,
    ) -> None:
        """Register a factory function for instantiating a BaseTool by tool_id.

        Raises:
            DuplicateToolRegistrationError: If a factory/tool with the same version is registered.
            ValueError: If tool_id is empty or factory is not callable.
        """
        if not tool_id or not tool_id.strip():
            raise ValueError("tool_id cannot be empty")
        if not callable(factory):
            raise ValueError("factory must be a callable")

        if metadata is None:
            # Instantiate a sample tool to extract metadata if none provided
            sample = factory()
            self._validate_tool_metadata(sample)
            metadata = sample.metadata

        descriptor = ToolDescriptor(
            metadata=metadata,
            factory=factory,
            enabled=True,
            registration_state="REGISTERED",
        )

        with self._lock:
            version = descriptor.version
            if tool_id not in self._descriptors:
                self._descriptors[tool_id] = {}

            if version in self._descriptors[tool_id]:
                raise DuplicateToolRegistrationError(
                    f"Tool factory for '{tool_id}' version '{version}' is already registered"
                )

            self._descriptors[tool_id][version] = descriptor

    def resolve(self, tool_id: str, version: str | None = None) -> ToolDescriptor:
        """Resolve the ToolDescriptor for a tool_id, optionally filtering by version.

        Separates resolution (lookup returning a runtime descriptor) from execution.

        Raises:
            ToolNotRegisteredError: If tool_id is not registered.
            ToolVersionMismatchError: If version is specified and does not match any registered version.
        """
        with self._lock:
            if tool_id not in self._descriptors or not self._descriptors[tool_id]:
                raise ToolNotRegisteredError(
                    f"Tool '{tool_id}' is not registered"
                )

            versions_map = self._descriptors[tool_id]

            if version is not None:
                for reg_version, descriptor in versions_map.items():
                    if self._match_version(reg_version, version):
                        return descriptor
                raise ToolVersionMismatchError(
                    f"Tool '{tool_id}' version '{version}' does not match registered versions ({list(versions_map.keys())})"
                )

            # Default resolution: return latest/first registered version
            return next(iter(versions_map.values()))

    def get(self, tool_id: str, version: str | None = None) -> BaseTool:
        """Retrieve an executable BaseTool instance for tool_id (Backwards-compatibility lookup).

        Delegates to `DefaultToolExecutor().instantiate(self.resolve(tool_id, version))`.
        """
        descriptor = self.resolve(tool_id, version)
        return self._executor.instantiate(descriptor)

    def create_tool(self, tool_id: str, **kwargs: Any) -> BaseTool:
        """Create or resolve an executable BaseTool instance using its registered descriptor."""
        descriptor = self.resolve(tool_id)
        return self._executor.instantiate(descriptor, **kwargs)

    def exists(self, tool_id: str) -> bool:
        """Check if a tool_id is registered."""
        with self._lock:
            return tool_id in self._descriptors and len(self._descriptors[tool_id]) > 0

    def unregister(self, tool_id: str, version: str | None = None) -> None:
        """Unregister a tool descriptor by tool_id and optional version.

        Raises:
            ToolNotRegisteredError: If tool_id is not registered.
        """
        with self._lock:
            if tool_id not in self._descriptors or not self._descriptors[tool_id]:
                raise ToolNotRegisteredError(
                    f"Tool '{tool_id}' is not registered"
                )

            if version is not None:
                if version not in self._descriptors[tool_id]:
                    raise ToolNotRegisteredError(
                        f"Tool '{tool_id}' version '{version}' is not registered"
                    )
                del self._descriptors[tool_id][version]
                if not self._descriptors[tool_id]:
                    del self._descriptors[tool_id]
            else:
                del self._descriptors[tool_id]

    def clear(self) -> None:
        """Clear all registered tool descriptors."""
        with self._lock:
            self._descriptors.clear()

    def list_descriptors(self) -> tuple[ToolDescriptor, ...]:
        """Return an immutable tuple of all registered ToolDescriptors."""
        with self._lock:
            result = []
            for versions_map in self._descriptors.values():
                result.extend(versions_map.values())
            return tuple(result)

    def list_tools(self) -> tuple[BaseTool, ...]:
        """Return an immutable tuple of executable BaseTool instances."""
        with self._lock:
            result = []
            for descriptor in self.list_descriptors():
                if descriptor.enabled and descriptor.instance:
                    result.append(descriptor.instance)
            return tuple(result)

    def discover_tools(self) -> tuple[ToolMetadata, ...]:
        """Return defensive copies of ToolMetadata for all registered tool descriptors."""
        with self._lock:
            return tuple(
                descriptor.metadata.model_copy(deep=True)
                for descriptor in self.list_descriptors()
                if descriptor.enabled
            )

    def _match_version(self, actual: str, requested: str) -> bool:
        """Isolated version comparison logic preparing the registry for multi-version evolution."""
        # Exact semantic version string comparison
        return actual.strip() == requested.strip()

    def _validate_tool_metadata(self, tool: BaseTool) -> None:
        """Validate static metadata fields on a BaseTool instance."""
        if not hasattr(tool, "metadata") or tool.metadata is None:
            raise ToolMetadataValidationError("Tool instance is missing metadata property")

        identity = getattr(tool.metadata, "identity", None)
        if identity is None:
            raise ToolMetadataValidationError("Tool metadata is missing identity specification")

        tool_id = getattr(identity, "tool_id", None)
        if not tool_id or not isinstance(tool_id, str) or not tool_id.strip():
            raise ToolMetadataValidationError("Tool metadata identity must have a non-empty tool_id")

        name = getattr(identity, "name", None)
        if not name or not isinstance(name, str) or not name.strip():
            raise ToolMetadataValidationError("Tool metadata identity must have a non-empty name")
