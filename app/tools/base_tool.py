from abc import ABC, abstractmethod
from typing import Any
from collections.abc import Mapping

from app.models.tool_metadata import ToolMetadata


class BaseTool(ABC):
    """Base interface for executable platform tools."""

    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """Return security and operational metadata for this tool."""

    @property
    def tool_id(self) -> str:
        return self.metadata.identity.tool_id

    @abstractmethod
    def execute(
        self,
        parameters: Mapping[str, Any],
    ) -> Any:
        """Execute the tool with validated platform parameters."""
