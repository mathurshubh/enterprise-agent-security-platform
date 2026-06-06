from app.models.tool import Tool, ToolRiskLevel
from app.services.tool_service import (
    ToolAlreadyExistsError,
    ToolNotFoundError,
    ToolService,
)


def create_tool(tool_id: str = "file_read") -> Tool:
    return Tool(
        tool_id=tool_id,
        risk_level=ToolRiskLevel.LOW,
        required_permission="files:read",
        approval_required=False,
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

    try:
        service.register_tool(tool)
        assert False
    except ToolAlreadyExistsError:
        pass


def test_get_unknown_tool():
    service = ToolService()

    try:
        service.get_tool("missing-tool")
        assert False
    except ToolNotFoundError:
        pass


def test_list_tools():
    service = ToolService()

    service.register_tool(create_tool("file_read"))
    service.register_tool(create_tool("file_write"))

    tools = service.list_tools()

    assert len(tools) == 2