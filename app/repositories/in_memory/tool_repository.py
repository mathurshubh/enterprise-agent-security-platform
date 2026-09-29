"""InMemoryToolRepository — In-memory adapter for declarative Tool configuration (ADR-030)."""

from __future__ import annotations

from threading import RLock

from app.models.tool import Tool
from app.repositories.interfaces.tool_repository import ToolRepository


class InMemoryToolRepository(ToolRepository):
    """Thread-safe in-memory repository for declarative Tool configuration.

    Invariants:
    - Object Isolation: Stored and returned entities are defensive deep copies.
    - Configuration Only: Stores declarative Tool models (wrapping ToolMetadata).
      Never stores executable handles, instances, or factories.
    - Missing Records: Non-existent entities return None.
    - Thread-Safe: Synchronized via threading.RLock.
    - Versioned Identity: keyed by ``(tool_id, version)``, so two versions of one tool
      coexist rather than the later one replacing the earlier.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._tools: dict[tuple[str, str], Tool] = {}

    def get(self, tool_id: str, version: str) -> Tool | None:
        with self._lock:
            tool = self._tools.get((tool_id, version))
            if tool is None:
                return None
            return tool.model_copy(deep=True)

    def save(self, tool: Tool) -> None:
        with self._lock:
            self._tools[tool.identity] = tool.model_copy(deep=True)

    def list(self) -> list[Tool]:
        with self._lock:
            return [t.model_copy(deep=True) for t in self._tools.values()]

    def list_versions(self, tool_id: str) -> list[Tool]:
        with self._lock:
            return [
                tool.model_copy(deep=True)
                for (family, _version), tool in self._tools.items()
                if family == tool_id
            ]
