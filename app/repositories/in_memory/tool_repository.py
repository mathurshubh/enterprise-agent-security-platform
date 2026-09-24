"""InMemoryToolRepository — In-memory adapter for declarative Tool configuration (ADR-030)."""

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
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._tools: dict[str, Tool] = {}

    def get(self, tool_id: str) -> Tool | None:
        with self._lock:
            tool = self._tools.get(tool_id)
            if tool is None:
                return None
            return tool.model_copy(deep=True)

    def save(self, tool: Tool) -> None:
        with self._lock:
            self._tools[tool.tool_id] = tool.model_copy(deep=True)

    def list(self) -> list[Tool]:
        with self._lock:
            return [t.model_copy(deep=True) for t in self._tools.values()]
