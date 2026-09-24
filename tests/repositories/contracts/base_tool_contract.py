"""Reusable contract tests for ToolRepository implementations."""

import abc

from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.repositories.interfaces.tool_repository import ToolRepository


class BaseToolRepositoryContractTests(abc.ABC):
    """Abstract contract test suite for any ToolRepository adapter."""

    @abc.abstractmethod
    def create_repository(self) -> ToolRepository:
        """Factory method to construct a fresh, empty repository under test."""
        raise NotImplementedError

    def _sample_tool(self, tool_id: str = "tool-1", name: str = "Tool 1") -> Tool:
        return Tool(
            metadata=ToolMetadata(
                identity=ToolIdentity(
                    tool_id=tool_id, name=name, description="A tool description"
                ),
                governance=ToolGovernance(
                    risk_level=ToolRiskLevel.LOW,
                    required_permissions=["file.read"],
                ),
                capability=ToolCapability(category="filesystem", reads_files=True),
                operational=ToolOperational(),
            )
        )

    def test_save_and_get_tool(self) -> None:
        repo = self.create_repository()
        tool = self._sample_tool()

        repo.save(tool)
        retrieved = repo.get(tool.tool_id)

        assert retrieved is not None
        assert retrieved.tool_id == tool.tool_id
        assert retrieved.metadata.identity.name == tool.metadata.identity.name
        assert (
            retrieved.metadata.governance.risk_level
            == tool.metadata.governance.risk_level
        )

    def test_get_missing_tool_returns_none(self) -> None:
        repo = self.create_repository()
        assert repo.get("non-existent-tool") is None

    def test_list_tools_empty_and_populated(self) -> None:
        repo = self.create_repository()
        assert repo.list() == []

        t1 = self._sample_tool("tool-1", "Tool 1")
        t2 = self._sample_tool("tool-2", "Tool 2")

        repo.save(t1)
        repo.save(t2)

        tools = repo.list()
        assert len(tools) == 2
        tool_ids = {t.tool_id for t in tools}
        assert tool_ids == {"tool-1", "tool-2"}

    def test_save_defensive_copy_isolation(self) -> None:
        """Mutating source metadata permissions after save must not affect repository state."""
        repo = self.create_repository()
        tool = self._sample_tool("tool-iso-1")
        repo.save(tool)

        # Mutate local permissions list
        tool.metadata.governance.required_permissions.append("tampered.perm")

        retrieved = repo.get("tool-iso-1")
        assert retrieved is not None
        assert "tampered.perm" not in retrieved.metadata.governance.required_permissions

    def test_get_defensive_copy_isolation(self) -> None:
        """Mutating retrieved metadata permissions must not affect repository state."""
        repo = self.create_repository()
        tool = self._sample_tool("tool-iso-2")
        repo.save(tool)

        retrieved1 = repo.get("tool-iso-2")
        assert retrieved1 is not None
        retrieved1.metadata.governance.required_permissions.append("tampered.perm")

        retrieved2 = repo.get("tool-iso-2")
        assert retrieved2 is not None
        assert (
            "tampered.perm" not in retrieved2.metadata.governance.required_permissions
        )

    def test_list_collection_isolation(self) -> None:
        """Mutating the list returned by list() must not affect subsequent queries."""
        repo = self.create_repository()
        tool = self._sample_tool("tool-iso-3")
        repo.save(tool)

        tools = repo.list()
        tools.clear()

        assert len(repo.list()) == 1
