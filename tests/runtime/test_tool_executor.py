import pytest

from app.models.runtime_context import RuntimeContext
from app.models.tool_capability import ToolCapability
from app.models.tool_descriptor import ToolDescriptor
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.runtime.tool_executor import (
    DefaultToolExecutor,
    ToolDisabledError,
    ToolExecutionError,
)
from app.tools.base_tool import BaseTool


class ExecutionTestTool(BaseTool):
    def __init__(self, tool_id: str = "exec_test", should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self._metadata = ToolMetadata(
            identity=ToolIdentity(
                tool_id=tool_id,
                name="Execution Test Tool",
                version="1.0.0",
                description="Testing ToolExecutor",
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
        if self.should_fail:
            raise RuntimeError("Underlying tool failure")
        return {"executed": True, **parameters}


def test_tool_executor_instantiate_from_instance():
    executor = DefaultToolExecutor()
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)

    instantiated = executor.instantiate(descriptor)
    assert instantiated is tool


def test_tool_executor_instantiate_from_factory():
    executor = DefaultToolExecutor()
    descriptor = ToolDescriptor(
        metadata=ExecutionTestTool().metadata,
        factory=lambda **kwargs: ExecutionTestTool(),
    )

    instantiated = executor.instantiate(descriptor)
    assert isinstance(instantiated, ExecutionTestTool)


def test_tool_executor_instantiate_disabled_raises_error():
    executor = DefaultToolExecutor()
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool, enabled=False)

    with pytest.raises(ToolDisabledError, match="disabled"):
        executor.instantiate(descriptor)


def test_tool_executor_instantiate_missing_instance_and_factory_raises_error():
    executor = DefaultToolExecutor()
    descriptor = ToolDescriptor(metadata=ExecutionTestTool().metadata)

    with pytest.raises(ToolExecutionError, match="neither a BaseTool instance nor a factory"):
        executor.instantiate(descriptor)


def test_tool_executor_execute_descriptor_success():
    executor = DefaultToolExecutor()
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)

    context = RuntimeContext(
        session_id="s1",
        request_id="r1",
        user_id="u1",
        principal="p1",
        authenticated_agent="a1",
    )

    result = executor.execute_descriptor(descriptor, {"param": "val"}, context)
    assert result == {"executed": True, "param": "val"}


def test_tool_executor_execute_translation_of_exceptions():
    executor = DefaultToolExecutor()
    tool = ExecutionTestTool(should_fail=True)
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)

    with pytest.raises(ToolExecutionError) as exc_info:
        executor.execute_descriptor(descriptor, {})

    assert "Underlying tool failure" in str(exc_info.value)
    assert exc_info.value.tool_id == "exec_test"
    assert isinstance(exc_info.value.cause, RuntimeError)
