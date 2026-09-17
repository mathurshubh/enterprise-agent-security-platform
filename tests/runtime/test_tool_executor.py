import pytest

from app.models.audit_event import Decision
from app.models.execution_binding import ExecutionBinding
from app.models.runtime_context import RuntimeContext
from app.models.tool_capability import ToolCapability
from app.models.tool_descriptor import ToolDescriptor
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.runtime.execution_authority import (
    ExecutionAuthority,
    ExecutionBindingError,
    ExecutionRefusalReason,
)
from app.runtime.tool_executor import (
    DefaultToolExecutor,
    ToolDisabledError,
    ToolExecutionError,
)
from app.tools.base_tool import BaseTool


class ExecutionTestTool(BaseTool):
    def __init__(self, tool_id: str = "exec_test", should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.executions = 0
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
        self.executions += 1
        if self.should_fail:
            raise RuntimeError("Underlying tool failure")
        return {"executed": True, **parameters}


def _grant_for(authority: ExecutionAuthority, tool_id: str, parameters: dict[str, str]):
    return authority.issue(
        ExecutionBinding.from_operation(tool_id, parameters),
        Decision.ALLOW,
    )


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
    authority = ExecutionAuthority()
    executor = DefaultToolExecutor(authority=authority)
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)

    context = RuntimeContext(
        session_id="s1",
        request_id="r1",
        user_id="u1",
        principal="p1",
        authenticated_agent="a1",
    )
    grant = _grant_for(authority, tool.tool_id, {"param": "val"})

    result = executor.execute_descriptor(descriptor, {"param": "val"}, context, grant=grant)
    assert result == {"executed": True, "param": "val"}


def test_tool_executor_execute_translation_of_exceptions():
    authority = ExecutionAuthority()
    executor = DefaultToolExecutor(authority=authority)
    tool = ExecutionTestTool(should_fail=True)
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(authority, tool.tool_id, {})

    with pytest.raises(ToolExecutionError) as exc_info:
        executor.execute_descriptor(descriptor, {}, grant=grant)

    assert "Underlying tool failure" in str(exc_info.value)
    assert exc_info.value.tool_id == "exec_test"
    assert isinstance(exc_info.value.cause, RuntimeError)


# ── ADR-023 execution trust boundary ─────────────────────────────────────────


def test_execute_tool_enforces_the_grant_as_well():
    authority = ExecutionAuthority()
    executor = DefaultToolExecutor(authority=authority)
    tool = ExecutionTestTool()

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_tool(tool, {"param": "val"})
    assert exc_info.value.reason is ExecutionRefusalReason.MISSING_GRANT
    assert tool.executions == 0

    grant = _grant_for(authority, tool.tool_id, {"param": "val"})
    assert executor.execute_tool(tool, {"param": "val"}, grant=grant) == {
        "executed": True,
        "param": "val",
    }


def test_executor_without_an_authority_refuses_every_execution():
    executor = DefaultToolExecutor()
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(ExecutionAuthority(), tool.tool_id, {"param": "val"})

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {"param": "val"}, grant=grant)

    assert exc_info.value.reason is ExecutionRefusalReason.NO_AUTHORITY
    assert tool.executions == 0


def test_executor_refuses_execution_without_a_grant():
    executor = DefaultToolExecutor(authority=ExecutionAuthority())
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {"param": "val"})

    assert exc_info.value.reason is ExecutionRefusalReason.MISSING_GRANT
    assert tool.executions == 0


def test_refusal_is_not_reported_as_a_tool_execution_failure():
    executor = DefaultToolExecutor(authority=ExecutionAuthority())
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {"param": "val"})

    assert not isinstance(exc_info.value, ToolExecutionError)
    assert isinstance(exc_info.value, PermissionError)


def test_disabled_tool_is_rejected_before_the_grant_is_consumed():
    authority = ExecutionAuthority()
    executor = DefaultToolExecutor(authority=authority)
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool, enabled=False)
    grant = _grant_for(authority, tool.tool_id, {"param": "val"})

    with pytest.raises(ToolDisabledError):
        executor.execute_descriptor(descriptor, {"param": "val"}, grant=grant)

    assert authority.outstanding_grant_count == 1


def test_non_string_parameters_are_refused_as_an_invalid_request():
    authority = ExecutionAuthority()
    executor = DefaultToolExecutor(authority=authority)
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(authority, tool.tool_id, {"param": "val"})

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {"param": 1}, grant=grant)

    assert exc_info.value.reason is ExecutionRefusalReason.INVALID_REQUEST
    assert tool.executions == 0


def test_grant_is_consumed_once_verified_even_if_the_tool_then_fails():
    authority = ExecutionAuthority()
    executor = DefaultToolExecutor(authority=authority)
    tool = ExecutionTestTool(should_fail=True)
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(authority, tool.tool_id, {})

    with pytest.raises(ToolExecutionError):
        executor.execute_descriptor(descriptor, {}, grant=grant)

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {}, grant=grant)

    assert exc_info.value.reason is ExecutionRefusalReason.CONSUMED
    assert tool.executions == 1
