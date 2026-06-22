from abc import ABC, abstractmethod

from app.models.tool_invocation import ToolInvocation


class EnterpriseAgent(ABC):
    @abstractmethod
    def invoke(
        self,
        query: str,
    ) -> ToolInvocation:
        """Convert a user request into a ToolInvocation."""