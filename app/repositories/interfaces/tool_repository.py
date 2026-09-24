"""ToolRepository — Domain persistence protocol for declarative Tool configuration (ADR-030)."""

from typing import Protocol

from app.models.tool import Tool


class ToolRepository(Protocol):
    """Repository protocol for declarative Tool configuration persistence (ADR-030).

    Invariants:
    - Configuration Plane: Persists declarative Tool / ToolMetadata configuration only.
    - Architectural Boundary: The repository MUST NEVER persist factory callables,
      tool_class references, or live instance handles from ToolDescriptor.
    - Executable tool resolution, instantiation, and execution remain exclusively
      in-memory within ToolRegistry and DefaultToolExecutor.
    """

    def get(self, tool_id: str) -> Tool | None:
        """Retrieve declarative Tool configuration by tool_id, or None if not found."""
        ...

    def save(self, tool: Tool) -> None:
        """Persist or update declarative Tool configuration."""
        ...

    def list(self) -> list[Tool]:
        """List all persisted declarative Tool configurations."""
        ...
