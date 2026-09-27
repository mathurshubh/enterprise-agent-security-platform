import ast
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.models.audit_event import Decision
from app.models.execution_binding import ExecutionBinding
from app.models.execution_capability import (
    ExecutionCapabilities,
    FilesystemCapability,
    NetworkCapability,
    ResourceLimits,
)
from app.models.execution_receipt import ExecutionStatus
from app.models.runtime_context import RuntimeContext
from app.models.sandbox_execution_result import SandboxExecutionResult
from app.models.tool_capability import ToolCapability
from app.models.tool_descriptor import ToolDescriptor
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.runtime.capability_registry import InMemoryCapabilityProfileRegistry
from app.runtime.exceptions import (
    CapabilityDigestMismatchError,
    CapabilityProfileNotFoundError,
    SandboxIsolationError,
    SandboxResourceExhaustedError,
    SandboxTimeoutError,
    SandboxUnavailableError,
)
from app.runtime.execution_authority import (
    ExecutionAuthority,
    ExecutionBindingError,
    ExecutionRefusalReason,
)
from app.runtime.sandbox.process_sandbox import ProcessToolExecutionSandbox
from app.runtime.tool_executor import (
    DefaultToolExecutor,
    ToolDisabledError,
    ToolExecutionError,
)
from app.services.execution_evidence_service import ExecutionEvidenceService
from app.tools.base_tool import BaseTool


class ExecutionTestTool(BaseTool):
    """Test tool conforming to BaseTool interface."""

    def __init__(
        self,
        tool_id: str = "exec_test",
        implementation_id: str = "test_echo",
        should_fail: bool = False,
    ) -> None:
        self.should_fail = should_fail
        self.implementation_id = implementation_id
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


def _make_test_capabilities(profile_id: str = "test-profile") -> ExecutionCapabilities:
    return ExecutionCapabilities(
        capability_profile_id=profile_id,
        filesystem=FilesystemCapability(
            workspace_root="/tmp",
            read_only=True,
        ),
        environment_variables={},
        network=NetworkCapability(),
        resources=ResourceLimits(),
    )


class StubSandbox:
    """Stub sandbox implementation conforming to ToolExecutionSandboxProtocol."""

    def __init__(
        self,
        should_fail: bool = False,
        fail_type: str = "RuntimeError",
        error_msg: str = "Underlying tool failure",
        raise_direct: Exception | None = None,
    ) -> None:
        self.should_fail = should_fail
        self.fail_type = fail_type
        self.error_msg = error_msg
        self.raise_direct = raise_direct
        self.executions = 0
        self.last_capabilities: ExecutionCapabilities | None = None

    def execute(
        self,
        *,
        tool: BaseTool,
        parameters: dict[str, Any],
        capabilities: ExecutionCapabilities,
        context: RuntimeContext,
    ) -> SandboxExecutionResult:
        self.executions += 1
        self.last_capabilities = capabilities

        if self.raise_direct is not None:
            raise self.raise_direct

        if self.should_fail:
            return SandboxExecutionResult(
                success=False,
                error_type=self.fail_type,
                error_message=self.error_msg,
            )

        return SandboxExecutionResult(
            success=True,
            output={"executed": True, **dict(parameters)},
        )


def _grant_for(
    authority: ExecutionAuthority,
    tool_id: str,
    parameters: dict[str, Any],
    profile_id: str | None = "test-profile",
    digest: str | None = None,
    agent_id: str = "agent-1",
    session_id: str = "session-1",
):
    if profile_id is not None and digest is None:
        caps = _make_test_capabilities(profile_id)
        digest = caps.compute_digest()
    return authority.issue(
        ExecutionBinding.from_operation(tool_id, parameters),
        Decision.ALLOW,
        agent_id=agent_id,
        session_id=session_id,
        capability_profile_id=profile_id,
        capability_digest=digest,
    )


def _make_executor(
    authority: ExecutionAuthority | None = None,
    sandbox: Any | None = None,
    registry: Any | None = None,
    evidence_store: Any | None = None,
    telemetry_emitter: Any | None = None,
    profile_id: str = "test-profile",
) -> DefaultToolExecutor:
    caps = _make_test_capabilities(profile_id)
    if registry is None:
        registry = InMemoryCapabilityProfileRegistry({profile_id: caps})
    if sandbox is None:
        sandbox = StubSandbox()
    return DefaultToolExecutor(
        authority=authority,
        evidence_store=evidence_store,
        telemetry_emitter=telemetry_emitter,
        sandbox=sandbox,
        capability_registry=registry,
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

    with pytest.raises(
        ToolExecutionError, match="neither a BaseTool instance nor a factory"
    ):
        executor.instantiate(descriptor)


def test_tool_executor_execute_descriptor_success():
    authority = ExecutionAuthority()
    executor = _make_executor(authority=authority)
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)

    grant = _grant_for(
        authority, tool.tool_id, {"param": "val"}, agent_id="a1", session_id="s1"
    )
    context = RuntimeContext(
        session_id="s1",
        request_id="r1",
        user_id="u1",
        principal="p1",
        authenticated_agent="a1",
    )

    result = executor.execute_descriptor(
        descriptor, {"param": "val"}, context, grant=grant
    )
    assert result == {"executed": True, "param": "val"}


def test_tool_executor_execute_translation_of_exceptions():
    authority = ExecutionAuthority()
    sandbox = StubSandbox(should_fail=True, error_msg="Underlying tool failure")
    executor = _make_executor(authority=authority, sandbox=sandbox)
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(authority, tool.tool_id, {})

    with pytest.raises(ToolExecutionError) as exc_info:
        executor.execute_descriptor(descriptor, {}, grant=grant)

    assert "Underlying tool failure" in str(exc_info.value)
    assert exc_info.value.tool_id == "exec_test"


# ── ADR-023 execution trust boundary ─────────────────────────────────────────


def test_execute_tool_enforces_the_grant_as_well():
    authority = ExecutionAuthority()
    executor = _make_executor(authority=authority)
    tool = ExecutionTestTool()

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_tool(tool, {"param": "val"})
    assert exc_info.value.reason is ExecutionRefusalReason.MISSING_GRANT

    grant = _grant_for(authority, tool.tool_id, {"param": "val"})
    assert executor.execute_tool(tool, {"param": "val"}, grant=grant) == {
        "executed": True,
        "param": "val",
    }


def test_executor_without_an_authority_refuses_every_execution():
    executor = _make_executor(authority=None)
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(ExecutionAuthority(), tool.tool_id, {"param": "val"})

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {"param": "val"}, grant=grant)

    assert exc_info.value.reason is ExecutionRefusalReason.NO_AUTHORITY


def test_executor_refuses_execution_without_a_grant():
    executor = _make_executor(authority=ExecutionAuthority())
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {"param": "val"})

    assert exc_info.value.reason is ExecutionRefusalReason.MISSING_GRANT


def test_refusal_is_not_reported_as_a_tool_execution_failure():
    executor = _make_executor(authority=ExecutionAuthority())
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {"param": "val"})

    assert not isinstance(exc_info.value, ToolExecutionError)
    assert isinstance(exc_info.value, PermissionError)


def test_disabled_tool_is_rejected_before_the_grant_is_consumed():
    authority = ExecutionAuthority()
    executor = _make_executor(authority=authority)
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool, enabled=False)
    grant = _grant_for(authority, tool.tool_id, {"param": "val"})

    with pytest.raises(ToolDisabledError):
        executor.execute_descriptor(descriptor, {"param": "val"}, grant=grant)

    assert authority.outstanding_grant_count == 1


def test_non_string_parameters_are_refused_as_an_invalid_request():
    authority = ExecutionAuthority()
    executor = _make_executor(authority=authority)
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(authority, tool.tool_id, {"param": "val"})

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {"param": 1}, grant=grant)

    assert exc_info.value.reason is ExecutionRefusalReason.INVALID_REQUEST


def test_grant_is_consumed_once_verified_even_if_the_tool_then_fails():
    authority = ExecutionAuthority()
    sandbox = StubSandbox(should_fail=True)
    executor = _make_executor(authority=authority, sandbox=sandbox)
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(authority, tool.tool_id, {})

    with pytest.raises(ToolExecutionError):
        executor.execute_descriptor(descriptor, {}, grant=grant)

    with pytest.raises(ExecutionBindingError) as exc_info:
        executor.execute_descriptor(descriptor, {}, grant=grant)

    assert exc_info.value.reason is ExecutionRefusalReason.CONSUMED
    assert sandbox.executions == 1


def test_tool_executor_records_started_and_succeeded_receipt():
    authority = ExecutionAuthority()
    store = ExecutionEvidenceService()
    executor = _make_executor(authority=authority, evidence_store=store)

    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(
        authority,
        tool.tool_id,
        {"msg": "hello"},
        agent_id="agent-1",
        session_id="sess-xyz",
    )
    context = RuntimeContext(
        session_id="sess-xyz",
        request_id="req-123",
        user_id="user-1",
        principal="agent-1",
        authenticated_agent="agent-1",
    )

    result = executor.execute_descriptor(
        descriptor, {"msg": "hello"}, context=context, grant=grant
    )
    assert result == {"executed": True, "msg": "hello"}

    receipt = store.get_by_grant(grant.grant_id)
    assert receipt is not None
    assert receipt.status == ExecutionStatus.SUCCEEDED
    # Evidence identity is the grant's, not the context's. Asserting the context value
    # is what let the "unspecified" fallback ship unnoticed.
    assert receipt.session_id == grant.session_id
    assert receipt.agent_id == grant.agent_id
    assert receipt.tool_id == tool.tool_id
    assert receipt.completed_at is not None
    assert receipt.duration_ms is not None and receipt.duration_ms >= 0
    assert receipt.output_digest is not None
    assert receipt.error_type is None
    assert len(store.list_open()) == 0


def test_tool_executor_records_failed_receipt_and_strips_raw_message_n3_7():
    """N3-7: Raw error messages must not enter the durable evidence record."""
    authority = ExecutionAuthority()
    store = ExecutionEvidenceService()
    sandbox = StubSandbox(
        should_fail=True,
        fail_type="RuntimeError",
        error_msg="Underlying tool failure",
    )
    executor = _make_executor(
        authority=authority, evidence_store=store, sandbox=sandbox
    )

    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(
        authority, tool.tool_id, {}, agent_id="agent-1", session_id="sess-fail"
    )
    context = RuntimeContext(
        session_id="sess-fail",
        request_id="req-fail",
        user_id="user-1",
        principal="agent-1",
        authenticated_agent="agent-1",
    )

    with pytest.raises(ToolExecutionError, match="Underlying tool failure"):
        executor.execute_descriptor(descriptor, {}, context=context, grant=grant)

    receipt = store.get_by_grant(grant.grant_id)
    assert receipt is not None
    assert receipt.status == ExecutionStatus.FAILED
    assert receipt.error_type == "RuntimeError"
    assert receipt.error_code == "TOOL_EXECUTION_ERROR"
    # Diagnostic safety: raw error string "Underlying tool failure" is not stored
    assert not hasattr(receipt, "error_message") or receipt.error_message is None
    assert len(store.list_open()) == 0


def test_instantiation_failure_does_not_create_started_receipt_n3_2():
    """N3-2: Instantiation failure consumes grant but never records STARTED."""
    authority = ExecutionAuthority()
    store = ExecutionEvidenceService()
    executor = _make_executor(authority=authority, evidence_store=store)

    # Tool factory that raises an error on instantiation
    def broken_factory(**kwargs):
        raise ValueError("Factory broken")

    descriptor = ToolDescriptor(
        metadata=ExecutionTestTool().metadata, factory=broken_factory
    )
    grant = _grant_for(authority, descriptor.tool_id, {})

    with pytest.raises(ValueError, match="Factory broken"):
        executor.execute_descriptor(descriptor, {}, grant=grant)

    # Grant is consumed
    assert authority.outstanding_grant_count == 0
    # But NO receipt was recorded (never reached execution boundary)
    assert store.get_by_grant(grant.grant_id) is None
    assert len(store.list_open()) == 0


def test_tool_executor_fails_closed_if_store_record_started_fails_n3_3():
    """N3-3: If evidence store fails to record STARTED, tool execution is NOT entered."""
    authority = ExecutionAuthority()
    mock_store = MagicMock()
    mock_store.record_started.side_effect = RuntimeError("Store storage failed")
    sandbox = StubSandbox()

    executor = _make_executor(
        authority=authority, evidence_store=mock_store, sandbox=sandbox
    )
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(authority, tool.tool_id, {})

    with pytest.raises(RuntimeError, match="Store storage failed"):
        executor.execute_descriptor(descriptor, {}, grant=grant)

    # Sandbox was never entered!
    assert sandbox.executions == 0


def test_telemetry_failure_does_not_block_execution_n3_6():
    """N3-6: Telemetry failure fails silent; does not block valid execution."""
    authority = ExecutionAuthority()
    store = ExecutionEvidenceService()
    mock_telemetry = MagicMock()
    mock_telemetry.emit.side_effect = RuntimeError("Telemetry pipeline down")

    executor = _make_executor(
        authority=authority,
        evidence_store=store,
        telemetry_emitter=mock_telemetry,
    )

    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(authority, tool.tool_id, {})

    # Execution completes normally despite telemetry failures
    result = executor.execute_descriptor(descriptor, {}, grant=grant)
    assert result == {"executed": True}

    receipt = store.get_by_grant(grant.grant_id)
    assert receipt is not None
    assert receipt.status.value == "SUCCEEDED"


# ── ADR-032 Runtime Tool Execution Isolation & Fail-Closed Gates ─────────────


def test_executor_fails_closed_when_sandbox_is_none():
    """ADR-032 / Gate 1: If no sandbox is configured, executor fails closed with SandboxUnavailableError."""
    authority = ExecutionAuthority()
    executor = DefaultToolExecutor(authority=authority, sandbox=None)
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    grant = _grant_for(authority, tool.tool_id, {})

    with pytest.raises(SandboxUnavailableError, match="No tool execution sandbox configured"):
        executor.execute_descriptor(descriptor, {}, grant=grant)

    # In-process tool was NEVER executed
    assert tool.executions == 0
    # Refusal happened before grant was consumed
    assert authority.outstanding_grant_count == 1


def test_executor_fails_closed_when_grant_missing_capability_profile():
    """ADR-032 / Gate 2: Grant lacking capability_profile_id fails closed with CapabilityProfileNotFoundError."""
    authority = ExecutionAuthority()
    executor = _make_executor(authority=authority)
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    # Issue grant with NO capability profile
    grant = _grant_for(authority, tool.tool_id, {}, profile_id=None)

    with pytest.raises(
        CapabilityProfileNotFoundError, match="does not have an explicit capability profile binding"
    ):
        executor.execute_descriptor(descriptor, {}, grant=grant)

    assert authority.outstanding_grant_count == 1


def test_executor_fails_closed_on_capability_digest_mismatch():
    """ADR-032 / Gate 3: Forged or modified capability snapshot fails closed with CapabilityDigestMismatchError."""
    authority = ExecutionAuthority()
    executor = _make_executor(authority=authority)
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    # Grant specifies a digest that doesn't match the profile's computed digest
    grant = _grant_for(
        authority, tool.tool_id, {}, profile_id="test-profile", digest="bad_digest_" * 4
    )

    with pytest.raises(CapabilityDigestMismatchError):
        executor.execute_descriptor(descriptor, {}, grant=grant)

    assert authority.outstanding_grant_count == 1


def test_executor_fails_closed_on_missing_capability_profile_in_registry():
    """ADR-032 / Gate 4: Unresolvable capability profile fails closed with CapabilityProfileNotFoundError."""
    authority = ExecutionAuthority()
    executor = _make_executor(authority=authority, profile_id="profile-alpha")
    tool = ExecutionTestTool()
    descriptor = ToolDescriptor(metadata=tool.metadata, instance=tool)
    # Grant bound to a profile that is NOT registered
    caps = _make_test_capabilities("profile-unregistered")
    grant = authority.issue(
        ExecutionBinding.from_operation(tool.tool_id, {}),
        Decision.ALLOW,
        agent_id="agent-1", session_id="session-1",
        capability_profile_id="profile-unregistered",
        capability_digest=caps.compute_digest(),
    )

    with pytest.raises(CapabilityProfileNotFoundError, match="is not registered"):
        executor.execute_descriptor(descriptor, {}, grant=grant)

    assert authority.outstanding_grant_count == 1


def test_tool_executor_records_distinct_failure_categories():
    """ADR-032 / Evidence: Distinguish TIMEOUT, RESOURCE_EXHAUSTED, ISOLATION_FAILURE, and TOOL_EXECUTION_ERROR."""
    authority = ExecutionAuthority()
    store = ExecutionEvidenceService()

    # 1. Timeout
    sandbox_timeout = StubSandbox(
        raise_direct=SandboxTimeoutError("Tool timed out", tool_id="t1", timeout_seconds=2.0)
    )
    exec_timeout = _make_executor(
        authority=authority, evidence_store=store, sandbox=sandbox_timeout
    )
    g1 = _grant_for(authority, "t1", {})
    with pytest.raises(ToolExecutionError):
        exec_timeout.execute_tool(ExecutionTestTool(tool_id="t1"), {}, grant=g1)
    r1 = store.get_by_grant(g1.grant_id)
    assert r1 is not None
    assert r1.status == ExecutionStatus.TIMEOUT
    assert r1.error_code == "EXECUTION_TIMEOUT"

    # 2. Resource Exhaustion
    sandbox_exhaust = StubSandbox(
        raise_direct=SandboxResourceExhaustedError("Output limit exceeded", tool_id="t2")
    )
    exec_exhaust = _make_executor(
        authority=authority, evidence_store=store, sandbox=sandbox_exhaust
    )
    g2 = _grant_for(authority, "t2", {})
    with pytest.raises(ToolExecutionError):
        exec_exhaust.execute_tool(ExecutionTestTool(tool_id="t2"), {}, grant=g2)
    r2 = store.get_by_grant(g2.grant_id)
    assert r2 is not None
    assert r2.status == ExecutionStatus.FAILED
    assert r2.error_code == "RESOURCE_EXHAUSTED"

    # 3. Isolation Failure
    sandbox_isolation = StubSandbox(
        raise_direct=SandboxIsolationError("Symlink escape detected", tool_id="t3")
    )
    exec_isolation = _make_executor(
        authority=authority, evidence_store=store, sandbox=sandbox_isolation
    )
    g3 = _grant_for(authority, "t3", {})
    with pytest.raises(ToolExecutionError):
        exec_isolation.execute_tool(ExecutionTestTool(tool_id="t3"), {}, grant=g3)
    r3 = store.get_by_grant(g3.grant_id)
    assert r3 is not None
    assert r3.status == ExecutionStatus.FAILED
    assert r3.error_code == "ISOLATION_FAILURE"


# Global sentinel to verify canary tool is never called in-process
CANARY_SENTINEL = {"invoked": False}


class AdversarialInProcessCanaryTool(BaseTool):
    """Tool whose execute() produces an in-process side effect if invoked in the host process."""

    def __init__(self) -> None:
        self.implementation_id = "test_echo"
        self._metadata = ToolMetadata(
            identity=ToolIdentity(
                tool_id="canary_tool",
                name="Canary Tool",
                version="1.0.0",
                description="Tests that tool.execute is never invoked in gateway process",
            ),
            governance=ToolGovernance(risk_level=ToolRiskLevel.LOW),
            capability=ToolCapability(category="test"),
            operational=ToolOperational(),
        )

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def execute(self, parameters: dict[str, object]) -> dict[str, object]:
        # If this method is called within the gateway process, the sentinel flips
        CANARY_SENTINEL["invoked"] = True
        return {"canary": "triggered"}


def test_adversarial_in_process_canary_not_invoked():
    """ADR-032 / Mandatory Proof: Assert that tool.execute() is NEVER invoked in the gateway process."""
    CANARY_SENTINEL["invoked"] = False

    authority = ExecutionAuthority()
    sandbox = ProcessToolExecutionSandbox()
    profile_id = "canary-profile"
    caps = _make_test_capabilities(profile_id)
    registry = InMemoryCapabilityProfileRegistry({profile_id: caps})

    executor = DefaultToolExecutor(
        authority=authority,
        sandbox=sandbox,
        capability_registry=registry,
    )

    canary = AdversarialInProcessCanaryTool()
    grant = authority.issue(
        ExecutionBinding.from_operation(canary.tool_id, {"message": "hello"}),
        Decision.ALLOW,
        agent_id="agent-1", session_id="session-1",
        capability_profile_id=profile_id,
        capability_digest=caps.compute_digest(),
    )

    result = executor.execute_tool(canary, {"message": "hello"}, grant=grant)

    # Subprocess runner executed the registered implementation "test_echo"
    assert result == "hello"
    # GATEWAY PROCESS SIDE EFFECT REMAINS COMPLETELY UNTOUCHED!
    assert CANARY_SENTINEL["invoked"] is False


def test_sandbox_pid_divergence():
    """ADR-032 / Mandatory Proof: Platform PID != Sandbox execution PID."""
    platform_pid = os.getpid()

    class PidTool(BaseTool):
        def __init__(self) -> None:
            self.implementation_id = "test_getpid"
            self._metadata = ToolMetadata(
                identity=ToolIdentity(
                    tool_id="pid_tool",
                    name="PID Tool",
                    version="1.0.0",
                    description="Returns execution PID",
                ),
                governance=ToolGovernance(risk_level=ToolRiskLevel.LOW),
                capability=ToolCapability(category="test"),
                operational=ToolOperational(),
            )

        @property
        def metadata(self) -> ToolMetadata:
            return self._metadata

        def execute(self, parameters: dict[str, object]) -> dict[str, object]:
            return {"pid": os.getpid()}

    authority = ExecutionAuthority()
    sandbox = ProcessToolExecutionSandbox()
    profile_id = "pid-profile"
    caps = _make_test_capabilities(profile_id)
    registry = InMemoryCapabilityProfileRegistry({profile_id: caps})

    executor = DefaultToolExecutor(
        authority=authority,
        sandbox=sandbox,
        capability_registry=registry,
    )

    tool = PidTool()
    grant = authority.issue(
        ExecutionBinding.from_operation(tool.tool_id, {}),
        Decision.ALLOW,
        agent_id="agent-1", session_id="session-1",
        capability_profile_id=profile_id,
        capability_digest=caps.compute_digest(),
    )

    result = executor.execute_tool(tool, {}, grant=grant)

    assert isinstance(result, dict)
    sandbox_pid = result.get("pid")
    assert sandbox_pid is not None
    # Proof: physical process separation
    assert sandbox_pid != platform_pid


def test_executor_has_no_in_process_execution_path():
    """AST / Static invariant: assert that DefaultToolExecutor does NOT call tool.execute(...)."""
    executor_file = Path(__file__).resolve().parent.parent.parent / "app" / "runtime" / "tool_executor.py"
    with open(executor_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(executor_file))

    for node in ast.walk(tree):
        # Check every method call in the file
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name == "execute":
                # Ensure no call is made to an object named "tool"
                if isinstance(node.func.value, ast.Name):
                    target_var = node.func.value.id
                    assert target_var != "tool", (
                        f"Violated ADR-032: Found illegal in-process call '{target_var}.execute(...)' "
                        f"at line {node.lineno} in {executor_file}"
                    )
