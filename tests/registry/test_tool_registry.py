import threading
import pytest

from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.models.tool_descriptor import ToolDescriptor
from app.registry.tool_registry import (
    DuplicateToolRegistrationError,
    ToolMetadataValidationError,
    ToolNotRegisteredError,
    ToolRegistry,
    ToolVersionMismatchError,
)
from app.tools.base_tool import BaseTool


class ExampleTool(BaseTool):
    def __init__(
        self,
        tool_id: str = "example_tool",
        version: str = "1.0.0",
        name: str = "Example Tool",
    ) -> None:
        self._metadata = ToolMetadata(
            identity=ToolIdentity(
                tool_id=tool_id,
                name=name,
                version=version,
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


class InvalidToolNoMetadata(BaseTool):
    @property
    def metadata(self) -> ToolMetadata:
        return None  # type: ignore[return-value]

    def execute(self, parameters: dict[str, object]) -> dict[str, object]:
        return parameters


class InvalidToolEmptyId(BaseTool):
    def __init__(self) -> None:
        self._metadata = ToolMetadata(
            identity=ToolIdentity(
                tool_id="",
                name="Empty ID Tool",
                description="Invalid tool",
            ),
            governance=ToolGovernance(
                risk_level=ToolRiskLevel.LOW,
            ),
            capability=ToolCapability(category="test"),
            operational=ToolOperational(),
        )

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def execute(self, parameters: dict[str, object]) -> dict[str, object]:
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


def test_resolve_returns_tool_descriptor():
    registry = ToolRegistry()
    tool = ExampleTool("res_tool", "1.2.0")

    registry.register(tool)

    descriptor = registry.resolve("res_tool")
    assert isinstance(descriptor, ToolDescriptor)
    assert descriptor.tool_id == "res_tool"
    assert descriptor.version == "1.2.0"
    assert descriptor.instance is tool
    from app.runtime.tool_executor import DefaultToolExecutor
    assert DefaultToolExecutor().instantiate(descriptor) is tool


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


def test_list_tools_returns_registered_tools_tuple():
    registry = ToolRegistry()
    first_tool = ExampleTool("first_tool")
    second_tool = ExampleTool("second_tool")

    registry.register(first_tool)
    registry.register(second_tool)

    assert list(registry.list_tools()) == [
        first_tool,
        second_tool,
    ]


def test_list_tools_returns_empty_tuple_when_registry_is_empty():
    registry = ToolRegistry()

    assert registry.list_tools() == ()


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
    assert list(registry.list_tools()) == [original_tool]


# ── Additional PR #69 Refinement Tests ───────────────────────────────────────


def test_register_validates_missing_metadata():
    registry = ToolRegistry()
    with pytest.raises(ToolMetadataValidationError, match="missing metadata"):
        registry.register(InvalidToolNoMetadata())


def test_register_validates_empty_tool_id():
    registry = ToolRegistry()
    with pytest.raises(ToolMetadataValidationError, match="non-empty tool_id"):
        registry.register(InvalidToolEmptyId())


def test_get_tool_version_matching():
    registry = ToolRegistry()
    tool = ExampleTool("ver_tool", version="2.1.0")
    registry.register(tool)

    assert registry.get("ver_tool", version="2.1.0") is tool

    with pytest.raises(ToolVersionMismatchError, match="does not match registered versions"):
        registry.get("ver_tool", version="1.0.0")


def test_factory_registration_and_creation():
    registry = ToolRegistry()
    registry.register_factory("fact_tool", lambda **kwargs: ExampleTool("fact_tool"))

    assert registry.exists("fact_tool") is True
    tool = registry.create_tool("fact_tool")
    assert tool.tool_id == "fact_tool"

    with pytest.raises(DuplicateToolRegistrationError):
        registry.register_factory("fact_tool", lambda **kwargs: ExampleTool("fact_tool"))


def test_create_tool_unregistered_raises_error():
    registry = ToolRegistry()
    with pytest.raises(ToolNotRegisteredError):
        registry.create_tool("unknown_tool")


def test_unregister_tool_and_factory():
    registry = ToolRegistry()
    registry.register(ExampleTool("unreg_tool"))
    assert registry.exists("unreg_tool") is True

    registry.unregister("unreg_tool")
    assert registry.exists("unreg_tool") is False

    with pytest.raises(ToolNotRegisteredError):
        registry.unregister("unreg_tool")


def test_clear_registry():
    registry = ToolRegistry()
    registry.register(ExampleTool("tool1"))
    registry.register_factory("fact1", lambda **kwargs: ExampleTool("fact1"))

    registry.clear()
    assert registry.list_tools() == ()
    assert registry.exists("tool1") is False
    assert registry.exists("fact1") is False


def test_concurrent_tool_registrations_thread_safety():
    registry = ToolRegistry()
    threads = []
    errors = []

    def worker(i: int):
        try:
            tool = ExampleTool(f"thread_tool_{i}")
            registry.register(tool)
        except Exception as e:
            errors.append(e)

    for i in range(20):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(errors) == 0
    assert len(registry.list_tools()) == 20
