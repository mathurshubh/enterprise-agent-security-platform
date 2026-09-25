import pytest

from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.repositories.in_memory.tool_repository import InMemoryToolRepository
from app.services.tool_service import (
    ToolAlreadyExistsError,
    ToolNotFoundError,
    ToolService,
)


def create_tool(tool_id: str = "file_read") -> Tool:
    return Tool(
        metadata=ToolMetadata(
            identity=ToolIdentity(
                tool_id=tool_id,
                name=tool_id.replace("_", " ").title(),
                description="Test tool",
            ),
            governance=ToolGovernance(
                risk_level=ToolRiskLevel.LOW,
                required_permissions=["files:read"],
                approval_required=False,
            ),
            capability=ToolCapability(
                category="filesystem",
                reads_files=True,
            ),
            operational=ToolOperational(),
        )
    )


def test_requires_repository_dependency() -> None:
    with pytest.raises(TypeError):
        ToolService()  # type: ignore[call-arg]


def test_register_tool() -> None:
    repo = InMemoryToolRepository()
    service = ToolService(tool_repository=repo)
    tool = create_tool()
    registered = service.register_tool(tool)

    assert registered == tool
    assert service.get_tool("file_read") == tool
    assert repo.get("file_read") == tool
    assert not hasattr(service, "_tools")


def test_duplicate_tool_rejected() -> None:
    repo = InMemoryToolRepository()
    service = ToolService(tool_repository=repo)
    tool = create_tool()
    service.register_tool(tool)

    with pytest.raises(ToolAlreadyExistsError):
        service.register_tool(tool)


def test_get_unknown_tool() -> None:
    repo = InMemoryToolRepository()
    service = ToolService(tool_repository=repo)

    with pytest.raises(ToolNotFoundError):
        service.get_tool("missing-tool")


def test_list_tools() -> None:
    repo = InMemoryToolRepository()
    service = ToolService(tool_repository=repo)
    service.register_tool(create_tool("file_read"))
    service.register_tool(create_tool("file_write"))

    tools = service.list_tools()
    assert len(tools) == 2
    tool_ids = {t.tool_id for t in tools}
    assert tool_ids == {"file_read", "file_write"}


def test_disable_tool() -> None:
    repo = InMemoryToolRepository()
    service = ToolService(tool_repository=repo)
    service.register_tool(create_tool("file_read"))

    assert service.get_tool("file_read").enabled is True

    disabled = service.disable_tool("file_read")
    assert disabled.enabled is False
    assert disabled.metadata.operational.enabled is False

    # Check persistence in repository
    persisted = repo.get("file_read")
    assert persisted is not None
    assert persisted.enabled is False


def test_enable_tool() -> None:
    repo = InMemoryToolRepository()
    service = ToolService(tool_repository=repo)
    service.register_tool(create_tool("file_read"))
    service.disable_tool("file_read")
    assert service.get_tool("file_read").enabled is False

    enabled = service.enable_tool("file_read")
    assert enabled.enabled is True
    assert enabled.metadata.operational.enabled is True

    persisted = repo.get("file_read")
    assert persisted is not None
    assert persisted.enabled is True


def test_disable_nonexistent_tool_raises_not_found() -> None:
    repo = InMemoryToolRepository()
    service = ToolService(tool_repository=repo)

    with pytest.raises(ToolNotFoundError):
        service.disable_tool("missing-tool")


def test_enable_nonexistent_tool_raises_not_found() -> None:
    repo = InMemoryToolRepository()
    service = ToolService(tool_repository=repo)

    with pytest.raises(ToolNotFoundError):
        service.enable_tool("missing-tool")


def test_defensive_copying_on_read() -> None:
    repo = InMemoryToolRepository()
    service = ToolService(tool_repository=repo)
    service.register_tool(create_tool("file_read"))

    tool_1 = service.get_tool("file_read")
    tool_2 = service.get_tool("file_read")
    assert tool_1 == tool_2
    assert tool_1 is not tool_2


def test_defensive_copying_on_write() -> None:
    repo = InMemoryToolRepository()
    service = ToolService(tool_repository=repo)
    original_tool = create_tool("file_read")
    service.register_tool(original_tool)

    stored = service.get_tool("file_read")
    assert stored == original_tool
    assert stored is not original_tool
