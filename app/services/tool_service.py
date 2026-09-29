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
from app.models.tool_family_governance import ToolFamilyGovernance
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
        """Register one concrete tool version in the authoritative repository.

        Only an exact ``(tool_id, version)`` collision is a duplicate. A second version of
        an existing family is a new record, not a conflict: the family is what an agent is
        approved for, and versions of it are distinct implementations.
        """
        with self._lock:
            existing = self._tool_repository.get(tool.tool_id, tool.version)
            if existing is not None:
                raise ToolAlreadyExistsError(
                    f"Tool '{tool.tool_id}' version '{tool.version}' already exists"
                )

            self._tool_repository.save(tool)
            return tool.model_copy(deep=True)

    def get_tool(self, tool_id: str, version: str) -> Tool:
        """Retrieve one concrete tool version.

        The version is required. This service performs no implicit selection: a family
        with several versions has no single answer, and inventing one would make the
        implementation a caller reaches depend on storage order rather than on a choice.
        """
        with self._lock:
            tool = self._tool_repository.get(tool_id, version)
            if tool is None:
                raise ToolNotFoundError(
                    f"Tool '{tool_id}' version '{version}' not found"
                )
            return tool.model_copy(deep=True)

    def list_versions(self, tool_id: str) -> list[Tool]:
        """List every registered version of one family, empty if the family is unknown."""
        with self._lock:
            return [
                t.model_copy(deep=True)
                for t in self._tool_repository.list_versions(tool_id)
            ]

    def family_exists(self, tool_id: str) -> bool:
        """Whether any version of this family is registered.

        The family-level question authorization asks. It reads no operational state:
        whether a particular implementation may run is an enforceability question settled
        later, at containment, not a reason to refuse the agent's request here.
        """
        with self._lock:
            return bool(self._tool_repository.list_versions(tool_id))

    def get_family_governance(self, tool_id: str) -> ToolFamilyGovernance:
        """Return the governance projection policy evaluates for this family (D-1).

        The family's effective risk is the most restrictive ``risk_level`` across all its
        registered versions. Aggregation lives here rather than in the authorization
        decision so that authorization stays about authorization, and so richer family
        governance has one seam to grow from.

        Registered versions, not enabled ones: enablement is a containment concern, and
        letting it move this value would make disabling a version change what an agent is
        permitted to request.

        Raises:
            ToolNotFoundError: if no version of the family is registered.
        """
        with self._lock:
            versions = self._tool_repository.list_versions(tool_id)
            if not versions:
                raise ToolNotFoundError(f"Tool '{tool_id}' not found")
            return ToolFamilyGovernance(
                tool_id=tool_id,
                # Ordered by severity; the members are strings and would otherwise
                # compare lexicographically, making CRITICAL the *smallest*.
                risk_level=max(
                    (t.metadata.governance.risk_level for t in versions),
                    key=lambda level: level.severity,
                ),
            )

    def list_tools(self) -> list[Tool]:
        """List all managed declarative Tool configurations."""
        with self._lock:
            return [t.model_copy(deep=True) for t in self._tool_repository.list()]

    def disable_tool(self, tool_id: str, version: str) -> Tool:
        """Disable one concrete tool version by setting operational.enabled=False.

        Enablement is version-scoped: a family has no enabled flag, so disabling one
        version leaves its siblings untouched. Authorization does not read this — a
        disabled version is refused at containment (ADR-023 A'), which keeps operational
        disablement from reading as a revoked authorization.

        Note: Implemented via get -> mutate -> save. Concurrency-safe within a
        single process via service lock, but not concurrency-atomic across
        independent repository writers (concurrency-atomic lifecycle updates
        are reserved for future CAS repository contracts if required).
        """
        with self._lock:
            tool = self.get_tool(tool_id, version)
            updated_operational = tool.metadata.operational.model_copy(
                update={"enabled": False}
            )
            updated_metadata = tool.metadata.model_copy(
                update={"operational": updated_operational}
            )
            updated_tool = tool.model_copy(update={"metadata": updated_metadata})
            self._tool_repository.save(updated_tool)
            return updated_tool.model_copy(deep=True)

    def enable_tool(self, tool_id: str, version: str) -> Tool:
        """Enable one concrete tool version by setting operational.enabled=True.

        Note: Implemented via get -> mutate -> save. Concurrency-safe within a
        single process via service lock, but not concurrency-atomic across
        independent repository writers (concurrency-atomic lifecycle updates
        are reserved for future CAS repository contracts if required).
        """
        with self._lock:
            tool = self.get_tool(tool_id, version)
            updated_operational = tool.metadata.operational.model_copy(
                update={"enabled": True}
            )
            updated_metadata = tool.metadata.model_copy(
                update={"operational": updated_operational}
            )
            updated_tool = tool.model_copy(update={"metadata": updated_metadata})
            self._tool_repository.save(updated_tool)
            return updated_tool.model_copy(deep=True)
