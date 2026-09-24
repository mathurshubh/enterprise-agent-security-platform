"""AgentRepository — Domain persistence protocol for Agent configuration entities (ADR-030)."""

from typing import Protocol

from app.models.agent import Agent


class AgentRepository(Protocol):
    """Repository protocol for Agent configuration persistence (ADR-030).

    Invariants:
    - Configuration Plane: low-frequency administrative mutations.
    - Manages agent identity, lifecycle status, risk tier, and capabilities.
    """

    def get(self, agent_id: str) -> Agent | None:
        """Retrieve an Agent by agent_id, or None if not found."""
        ...

    def save(self, agent: Agent) -> None:
        """Persist or update an Agent entity."""
        ...

    def list(self) -> list[Agent]:
        """List all persisted Agent entities."""
        ...
