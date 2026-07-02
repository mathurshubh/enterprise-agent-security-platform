from collections.abc import Mapping
from typing import Any

from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.registry.tool_registry import ToolRegistry
from app.services.tool_inventory_service import ToolInventoryService
from app.tools.base_tool import BaseTool


class InventoryTool(BaseTool):
    def __init__(
        self,
        tool_id: str = "inventory_tool",
    ) -> None:
        self._metadata = ToolMetadata(
            identity=ToolIdentity(
                tool_id=tool_id,
                name=tool_id.replace(
                    "_",
                    " ",
                ).title(),
                description="Inventory test tool",
            ),
            governance=ToolGovernance(
                risk_level=ToolRiskLevel.LOW,
                required_permissions=[
                    "inventory:read",
                ],
            ),
            capability=ToolCapability(
                category="inventory",
            ),
            operational=ToolOperational(),
        )

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def execute(
        self,
        parameters: Mapping[str, Any],
    ) -> dict[str, object]:
        return dict(parameters)


def test_list_registered_tools_returns_metadata_tuple():
    registry = ToolRegistry()
    tool = InventoryTool()
    registry.register(tool)
    service = ToolInventoryService(registry)

    registered_tools = service.list_registered_tools()

    assert isinstance(
        registered_tools,
        tuple,
    )
    assert registered_tools == (
        tool.metadata,
    )


def test_list_registered_tools_returns_empty_tuple_when_registry_is_empty():
    service = ToolInventoryService(ToolRegistry())

    assert service.list_registered_tools() == ()


def test_list_registered_tools_preserves_registration_order():
    registry = ToolRegistry()
    registry.register(InventoryTool("first_tool"))
    registry.register(InventoryTool("second_tool"))
    service = ToolInventoryService(registry)

    registered_tools = service.list_registered_tools()

    assert [
        metadata.identity.tool_id
        for metadata in registered_tools
    ] == [
        "first_tool",
        "second_tool",
    ]


def test_list_registered_tools_does_not_expose_executable_tools():
    registry = ToolRegistry()
    registry.register(InventoryTool())
    service = ToolInventoryService(registry)

    registered_tools = service.list_registered_tools()

    assert isinstance(
        registered_tools[0],
        ToolMetadata,
    )
    assert not isinstance(
        registered_tools[0],
        BaseTool,
    )
    assert not hasattr(
        registered_tools[0],
        "execute",
    )


def test_list_registered_tools_returns_defensive_metadata_copies():
    registry = ToolRegistry()
    tool = InventoryTool("immutable_tool")
    registry.register(tool)
    service = ToolInventoryService(registry)

    registered_metadata = service.list_registered_tools()[0]
    registered_metadata.identity.name = "Changed Name"
    registered_metadata.governance.required_permissions.append(
        "extra:permission"
    )

    executable_tool = registry.get("immutable_tool")

    assert executable_tool.metadata.identity.name == "Immutable Tool"
    assert executable_tool.metadata.governance.required_permissions == [
        "inventory:read",
    ]


def test_list_registered_tools_does_not_modify_registry_contents():
    registry = ToolRegistry()
    first_tool = InventoryTool("first_tool")
    second_tool = InventoryTool("second_tool")
    registry.register(first_tool)
    registry.register(second_tool)
    service = ToolInventoryService(registry)

    service.list_registered_tools()

    assert registry.list_tools() == [
        first_tool,
        second_tool,
    ]


def test_list_registered_tools_reflects_later_registry_registrations():
    registry = ToolRegistry()
    service = ToolInventoryService(registry)

    assert service.list_registered_tools() == ()

    registry.register(InventoryTool("later_tool"))

    assert [
        metadata.identity.tool_id
        for metadata in service.list_registered_tools()
    ] == [
        "later_tool",
    ]

def test_list_registered_tools_returns_fresh_metadata_instances():
    registry = ToolRegistry()
    registry.register(InventoryTool("fresh_tool"))
    service = ToolInventoryService(registry)

    first_call = service.list_registered_tools()
    second_call = service.list_registered_tools()

    assert first_call is not second_call
    assert first_call[0] is not second_call[0]
    
