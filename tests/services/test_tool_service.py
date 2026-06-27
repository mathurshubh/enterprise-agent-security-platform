import pytest

from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
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
                name=tool_id.replace(
                    "_",
                    " ",
                ).title(),
                description="Test tool",
            ),
            governance=ToolGovernance(
                risk_level=ToolRiskLevel.LOW,
                required_permissions=[
                    "files:read",
                ],
                approval_required=False,
            ),
            capability=ToolCapability(
                category="filesystem",
                reads_files=True,
            ),
            operational=ToolOperational(),
        )
    )


def test_register_tool():
    service = ToolService()
    tool = create_tool()
    service.register_tool(tool)
    assert service.get_tool("file_read") == tool


def test_duplicate_tool_rejected():
    service = ToolService()
    tool = create_tool()
    service.register_tool(tool)
    with pytest.raises(ToolAlreadyExistsError):
        service.register_tool(tool)


def test_get_unknown_tool():
    service = ToolService()
    with pytest.raises(ToolNotFoundError):
        service.get_tool("missing-tool")


def test_list_tools():
    service = ToolService()
    service.register_tool(create_tool("file_read"))
    service.register_tool(create_tool("file_write"))
    tools = service.list_tools()
    assert len(tools) == 2
