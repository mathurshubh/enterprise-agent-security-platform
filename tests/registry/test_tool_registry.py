import pytest

from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.registry.tool_registry import (
    DuplicateToolRegistrationError,
    ToolNotRegisteredError,
    ToolRegistry,
)
from app.tools.base_tool import BaseTool


class ExampleTool(BaseTool):
    def __init__(
        self,
        tool_id: str = "example_tool",
    ) -> None:
        self._metadata = ToolMetadata(
            identity=ToolIdentity(
                tool_id=tool_id,
                name="Example Tool",
                description="Example executable tool",
            ),
            governance=ToolGovernance(
                risk_level=ToolRiskLevel.LOW,
                required_permissions=["example:execute"],
            ),
            capability=ToolCapability(
                category="example",
            ),
            operational=ToolOperational(),
        )

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def execute(
        self,
        parameters: dict[str, object],
    ) -> dict[str, object]:
        return parameters


def test_register_returns_registered_tool():
    registry = ToolRegistry()
    tool = ExampleTool()

    result = registry.register(tool)

    assert result is tool


def test_get_returns_registered_tool_by_id():
    registry = ToolRegistry()
    tool = ExampleTool()

    registry.register(tool)

    assert registry.get("example_tool") is tool


def test_get_unknown_tool_raises_error():
    registry = ToolRegistry()

    with pytest.raises(
        ToolNotRegisteredError,
        match="missing_tool",
    ):
        registry.get("missing_tool")


def test_exists_returns_true_for_registered_tool():
    registry = ToolRegistry()

    registry.register(ExampleTool())

    assert registry.exists("example_tool") is True


def test_exists_returns_false_for_unknown_tool():
    registry = ToolRegistry()

    assert registry.exists("missing_tool") is False


def test_list_tools_returns_registered_tools_in_registration_order():
    registry = ToolRegistry()
    first_tool = ExampleTool("first_tool")
    second_tool = ExampleTool("second_tool")

    registry.register(first_tool)
    registry.register(second_tool)

    assert registry.list_tools() == [
        first_tool,
        second_tool,
    ]


def test_list_tools_returns_empty_list_when_registry_is_empty():
    registry = ToolRegistry()

    assert registry.list_tools() == []


def test_discover_tools_returns_metadata_for_registered_tools():
    registry = ToolRegistry()
    tool = ExampleTool("discoverable_tool")

    registry.register(tool)

    discovered_tools = registry.discover_tools()

    assert len(discovered_tools) == 1
    assert discovered_tools[0] == tool.metadata
    assert (
        discovered_tools[0].identity.tool_id
        == "discoverable_tool"
    )


def test_discover_tools_returns_metadata_in_registration_order():
    registry = ToolRegistry()
    registry.register(ExampleTool("first_tool"))
    registry.register(ExampleTool("second_tool"))

    discovered_tools = registry.discover_tools()

    assert [
        metadata.identity.tool_id
        for metadata in discovered_tools
    ] == [
        "first_tool",
        "second_tool",
    ]


def test_discover_tools_returns_empty_tuple_when_registry_is_empty():
    registry = ToolRegistry()

    assert registry.discover_tools() == ()


def test_discover_tools_does_not_expose_executable_tools():
    registry = ToolRegistry()
    registry.register(ExampleTool())

    discovered_tools = registry.discover_tools()

    assert isinstance(
        discovered_tools[0],
        ToolMetadata,
    )
    assert not isinstance(
        discovered_tools[0],
        BaseTool,
    )
    assert not hasattr(
        discovered_tools[0],
        "execute",
    )


def test_discover_tools_returns_defensive_metadata_copies():
    registry = ToolRegistry()
    tool = ExampleTool("immutable_tool")
    registry.register(tool)

    discovered_metadata = registry.discover_tools()[0]
    discovered_metadata.identity.name = "Changed Name"
    discovered_metadata.governance.required_permissions.append(
        "extra:permission"
    )

    registered_metadata = registry.get(
        "immutable_tool"
    ).metadata

    assert registered_metadata.identity.name == "Example Tool"
    assert registered_metadata.governance.required_permissions == [
        "example:execute",
    ]


def test_register_rejects_duplicate_tool_ids():
    registry = ToolRegistry()
    registry.register(ExampleTool("duplicate_tool"))

    with pytest.raises(
        DuplicateToolRegistrationError,
        match="duplicate_tool",
    ):
        registry.register(ExampleTool("duplicate_tool"))


def test_rejected_duplicate_does_not_replace_original_tool():
    registry = ToolRegistry()
    original_tool = ExampleTool("duplicate_tool")
    duplicate_tool = ExampleTool("duplicate_tool")

    registry.register(original_tool)

    with pytest.raises(DuplicateToolRegistrationError):
        registry.register(duplicate_tool)

    assert registry.get("duplicate_tool") is original_tool
    assert registry.list_tools() == [original_tool]
