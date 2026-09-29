"""ToolRepository — Domain persistence protocol for declarative Tool configuration (ADR-030)."""

from __future__ import annotations

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
    - Versioned Identity: a tool is identified by ``(tool_id, version)``. ``tool_id``
      alone names a *family*, which is the unit an agent is approved for; it does not
      identify an implementation. Two versions of one tool are two records.
    - No Implicit Selection: nothing here resolves a family to one version. A caller that
      needs a concrete implementation names the version it means. A repository that chose
      one would make the answer depend on storage order.
    """

    def get(self, tool_id: str, version: str) -> Tool | None:
        """Retrieve one concrete tool version, or None if it is not registered."""
        ...

    def save(self, tool: Tool) -> None:
        """Persist or update one concrete tool version, keyed by ``(tool_id, version)``."""
        ...

    def list(self) -> list[Tool]:
        """List every persisted tool version across all families."""
        ...

    def list_versions(self, tool_id: str) -> list[Tool]:
        """List every persisted version of one family, empty if the family is unknown.

        The family-level query. Authorization uses its emptiness to establish that a
        family exists; it does not read operational state from the versions returned.
        """
        ...
