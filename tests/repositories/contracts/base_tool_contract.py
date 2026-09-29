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

    def _sample_tool(
        self,
        tool_id: str = "tool-1",
        name: str = "Tool 1",
        version: str = "1.0.0",
        risk_level: ToolRiskLevel = ToolRiskLevel.LOW,
    ) -> Tool:
        return Tool(
            metadata=ToolMetadata(
                identity=ToolIdentity(
                    tool_id=tool_id,
                    name=name,
                    version=version,
                    description="A tool description",
                ),
                governance=ToolGovernance(
                    risk_level=risk_level,
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
        retrieved = repo.get(tool.tool_id, tool.version)

        assert retrieved is not None
        assert retrieved.tool_id == tool.tool_id
        assert retrieved.metadata.identity.name == tool.metadata.identity.name
        assert (
            retrieved.metadata.governance.risk_level
            == tool.metadata.governance.risk_level
        )

    def test_get_missing_tool_returns_none(self) -> None:
        repo = self.create_repository()
        assert repo.get("non-existent-tool", "1.0.0") is None

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

        retrieved = repo.get("tool-iso-1", "1.0.0")
        assert retrieved is not None
        assert "tampered.perm" not in retrieved.metadata.governance.required_permissions

    def test_get_defensive_copy_isolation(self) -> None:
        """Mutating retrieved metadata permissions must not affect repository state."""
        repo = self.create_repository()
        tool = self._sample_tool("tool-iso-2")
        repo.save(tool)

        retrieved1 = repo.get("tool-iso-2", "1.0.0")
        assert retrieved1 is not None
        retrieved1.metadata.governance.required_permissions.append("tampered.perm")

        retrieved2 = repo.get("tool-iso-2", "1.0.0")
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


    # --- Versioned identity (D-1) -------------------------------------------------

    def test_two_versions_of_one_tool_are_two_records(self) -> None:
        """``(tool_id, version)`` is the identity; ``tool_id`` alone names a family."""
        repo = self.create_repository()
        v1 = self._sample_tool(tool_id="file_read", version="1.0.0")
        v2 = self._sample_tool(tool_id="file_read", version="2.0.0")

        repo.save(v1)
        repo.save(v2)

        assert repo.get("file_read", "1.0.0") is not None
        assert repo.get("file_read", "2.0.0") is not None
        assert len(repo.list()) == 2, "the later version must not replace the earlier"

    def test_a_version_is_addressed_exactly(self) -> None:
        repo = self.create_repository()
        repo.save(self._sample_tool(tool_id="file_read", version="1.0.0"))

        assert repo.get("file_read", "1.0.0") is not None
        assert repo.get("file_read", "9.9.9") is None, "no fallback to another version"

    def test_saving_the_same_version_replaces_it(self) -> None:
        repo = self.create_repository()
        repo.save(self._sample_tool(tool_id="file_read", version="1.0.0", name="Before"))
        repo.save(self._sample_tool(tool_id="file_read", version="1.0.0", name="After"))

        stored = repo.get("file_read", "1.0.0")
        assert stored is not None
        assert stored.metadata.identity.name == "After"
        assert len(repo.list()) == 1

    def test_list_versions_returns_one_family(self) -> None:
        repo = self.create_repository()
        repo.save(self._sample_tool(tool_id="file_read", version="1.0.0"))
        repo.save(self._sample_tool(tool_id="file_read", version="2.0.0"))
        repo.save(self._sample_tool(tool_id="shell_exec", version="1.0.0"))

        versions = repo.list_versions("file_read")

        assert sorted(t.version for t in versions) == ["1.0.0", "2.0.0"]
        assert all(t.tool_id == "file_read" for t in versions)

    def test_list_versions_of_an_unknown_family_is_empty(self) -> None:
        repo = self.create_repository()
        assert repo.list_versions("never-registered") == []
