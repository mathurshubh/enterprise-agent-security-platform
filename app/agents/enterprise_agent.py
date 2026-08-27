from abc import ABC, abstractmethod

from app.models.tool_invocation import ToolInvocation


class EnterpriseAgent(ABC):
    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Return the agent identity associated with this agent instance."""

    @abstractmethod
    def invoke(
        self,
        query: str,
    ) -> ToolInvocation:
        """Convert a user request into a ToolInvocation."""