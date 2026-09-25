"""ToolService — Domain service managing declarative Tool configurations (v0.16, PR #184).

Invariants:
- ToolRepository Authority: ToolRepository is the sole authoritative state source.
  ToolService owns zero internal storage collections or caching dictionaries.
- Declarative Plane: Manages declarative Tool configurations (ToolMetadata).
  Executable tool handles, factories, and instances remain exclusively process-local
  in ToolRegistry and DefaultToolExecutor.
- Fail-Closed: Parameterless construction raises TypeError; an explicit ToolRepository
  dependency is strictly required.
- Defensive Isolation: Returned and persisted Tool entities are isolated deep copies.
"""

from threading import RLock

from app.models.tool import Tool
from app.registry.tool_registry import ToolRegistry
from app.repositories.interfaces.tool_repository import ToolRepository


class ToolAlreadyExistsError(Exception):
    """Raised when attempting to register an existing tool."""


class ToolNotFoundError(Exception):
    """Raised when a tool cannot be found."""


class ToolService:
    """Domain service managing declarative Tool configurations backed by ToolRepository."""

    def __init__(
        self,
        tool_repository: ToolRepository,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._lock = RLock()
        self._tool_repository = tool_repository
        self._tool_registry = tool_registry

    @property
    def tool_repository(self) -> ToolRepository:
        """Injected ToolRepository protocol instance."""
        return self._tool_repository

    @property
    def tool_registry(self) -> ToolRegistry | None:
        """Injected ToolRegistry instance (if supplied)."""
        return self._tool_registry

    def register_tool(self, tool: Tool) -> Tool:
        """Register a declarative Tool in the authoritative repository."""
        with self._lock:
            existing = self._tool_repository.get(tool.tool_id)
            if existing is not None:
                raise ToolAlreadyExistsError(f"Tool '{tool.tool_id}' already exists")

            self._tool_repository.save(tool)
            return tool.model_copy(deep=True)

    def get_tool(self, tool_id: str) -> Tool:
        """Retrieve a declarative Tool configuration by tool_id."""
        with self._lock:
            tool = self._tool_repository.get(tool_id)
            if tool is None:
                raise ToolNotFoundError(f"Tool '{tool_id}' not found")
            return tool.model_copy(deep=True)

    def list_tools(self) -> list[Tool]:
        """List all managed declarative Tool configurations."""
        with self._lock:
            return [t.model_copy(deep=True) for t in self._tool_repository.list()]

    def disable_tool(self, tool_id: str) -> Tool:
        """Disable a tool by setting operational.enabled=False.

        Note: Implemented via get -> mutate -> save. Concurrency-safe within a
        single process via service lock, but not concurrency-atomic across
        independent repository writers (concurrency-atomic lifecycle updates
        are reserved for future CAS repository contracts if required).
        """
        with self._lock:
            tool = self.get_tool(tool_id)
            updated_operational = tool.metadata.operational.model_copy(
                update={"enabled": False}
            )
            updated_metadata = tool.metadata.model_copy(
                update={"operational": updated_operational}
            )
            updated_tool = tool.model_copy(update={"metadata": updated_metadata})
            self._tool_repository.save(updated_tool)
            return updated_tool.model_copy(deep=True)

    def enable_tool(self, tool_id: str) -> Tool:
        """Enable a tool by setting operational.enabled=True.

        Note: Implemented via get -> mutate -> save. Concurrency-safe within a
        single process via service lock, but not concurrency-atomic across
        independent repository writers (concurrency-atomic lifecycle updates
        are reserved for future CAS repository contracts if required).
        """
        with self._lock:
            tool = self.get_tool(tool_id)
            updated_operational = tool.metadata.operational.model_copy(
                update={"enabled": True}
            )
            updated_metadata = tool.metadata.model_copy(
                update={"operational": updated_operational}
            )
            updated_tool = tool.model_copy(update={"metadata": updated_metadata})
            self._tool_repository.save(updated_tool)
            return updated_tool.model_copy(deep=True)
