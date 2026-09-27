"""Tests for ProcessToolExecutionSandbox subprocess isolation and cleanup (ADR-032)."""

import os
import time
from typing import Any

import pytest

from app.models.execution_capability import (
    ExecutionCapabilities,
    FilesystemCapability,
    NetworkCapability,
    ResourceLimits,
)
from app.models.execution_provenance import ExecutionProvenance
from app.models.sandbox_execution_result import SandboxExecutionResult
from app.runtime.contracts import ToolExecutionSandboxProtocol
from app.runtime.exceptions import (
    SandboxResourceExhaustedError,
    SandboxTimeoutError,
)
from app.runtime.sandbox.process_sandbox import ProcessToolExecutionSandbox
from app.tools.base_tool import BaseTool


class MockTool(BaseTool):
    """Mock tool conforming to BaseTool interface for sandbox tests."""

    def __init__(self, tool_id: str, implementation_id: str | None = None) -> None:
        self._tool_id = tool_id
        self._implementation_id = implementation_id or f"{tool_id}_v1"

    @property
    def tool_id(self) -> str:
        return self._tool_id

    @property
    def implementation_id(self) -> str:
        return self._implementation_id

    @property
    def metadata(self) -> Any:
        return None

    def execute(self, parameters: dict[str, Any]) -> Any:
        # In-process method should not be called by sandbox
        raise NotImplementedError("Sandbox must execute child runner, not in-process method")


def _make_test_capabilities(
    timeout_seconds: float = 5.0,
    max_output_bytes: int = 64 * 1024,
    env: dict[str, str] | None = None,
) -> ExecutionCapabilities:
    return ExecutionCapabilities(
        capability_profile_id="test-sandbox-profile",
        filesystem=FilesystemCapability(
            workspace_root="/tmp",
            read_only=True,
        ),
        environment_variables=env or {},
        network=NetworkCapability(),
        resources=ResourceLimits(
            max_memory_bytes=256 * 1024 * 1024,
            max_cpu_seconds=5.0,
            max_output_bytes=max_output_bytes,
            wall_clock_timeout_seconds=timeout_seconds,
        ),
    )


def _make_provenance(
    session_id: str = "sess-1",
    agent_id: str = "agent-1",
    request_id: str = "req-1",
    grant_id: str = "grant-1",
) -> ExecutionProvenance:
    return ExecutionProvenance(
        grant_id=grant_id,
        agent_id=agent_id,
        session_id=session_id,
        request_id=request_id,
    )


class TestProcessToolExecutionSandboxProtocol:
    """Verifies that ProcessToolExecutionSandbox satisfies the protocol."""

    def test_satisfies_protocol(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        assert isinstance(sandbox, ToolExecutionSandboxProtocol)


class TestProcessSandboxExecution:
    """Verifies execution, clean environment, timeouts, and bounded output."""

    def test_successful_tool_execution(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_echo", implementation_id="test_echo")
        provenance = _make_provenance()
        caps = _make_test_capabilities()

        result = sandbox.execute(
            tool=tool,
            parameters={"message": "hello sandbox"},
            capabilities=caps,
            provenance=provenance,
        )

        assert isinstance(result, SandboxExecutionResult)
        assert result.success is True
        assert result.output == "hello sandbox"
        assert result.exit_code == 0
        assert result.output_digest is not None
        assert result.duration_ms >= 0

    def test_descriptor_carries_the_authoritative_grant_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The descriptor built for the child must carry the real grant id.

        It previously carried ``context.request_id`` under the name ``grant_id``, so the
        evidence store and the child payload disagreed about which grant authorized the
        execution. Asserted on the constructed descriptor rather than on the provenance
        handed in, because the defect was in this construction step.
        """
        import app.runtime.sandbox.descriptor as descriptor_module

        captured: dict[str, object] = {}
        real = descriptor_module.ToolExecutionDescriptor

        def _capturing(**kwargs: object):
            captured.update(kwargs)
            return real(**kwargs)

        monkeypatch.setattr(descriptor_module, "ToolExecutionDescriptor", _capturing)

        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_echo", implementation_id="test_echo")
        provenance = _make_provenance(
            grant_id="grant-authoritative",
            request_id="req-correlation",
            agent_id="agent-9",
            session_id="sess-9",
        )

        sandbox.execute(
            tool=tool,
            parameters={"message": "hi"},
            capabilities=_make_test_capabilities(),
            provenance=provenance,
        )

        assert captured["grant_id"] == "grant-authoritative"
        assert captured["request_id"] == "req-correlation"
        assert captured["grant_id"] != captured["request_id"]
        assert captured["agent_id"] == "agent-9"
        assert captured["session_id"] == "sess-9"

    def test_clean_room_environment_strips_platform_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Set dummy platform secrets in parent environment
        monkeypatch.setenv("POSTGRES_URL", "postgresql://admin:supersecret@db:5432/platform")
        monkeypatch.setenv("JWT_SECRET_KEY", "top_secret_signing_key_999")
        monkeypatch.setenv("SOME_RANDOM_PARENT_VAR", "uncontrolled_parent_state")

        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_env_dump", implementation_id="test_env_dump")
        provenance = _make_provenance()

        # Allow only EXPLICIT_ALLOWED_VAR
        caps = _make_test_capabilities(env={"EXPLICIT_ALLOWED_VAR": "safe_value"})

        result = sandbox.execute(
            tool=tool,
            parameters={"keys": ["POSTGRES_URL", "JWT_SECRET_KEY", "SOME_RANDOM_PARENT_VAR", "EXPLICIT_ALLOWED_VAR"]},
            capabilities=caps,
            provenance=provenance,
        )

        assert result.success is True
        env_dump = result.output
        assert isinstance(env_dump, dict)
        # Verify parent secrets are completely stripped
        assert env_dump["POSTGRES_URL"] is None
        assert env_dump["JWT_SECRET_KEY"] is None
        assert env_dump["SOME_RANDOM_PARENT_VAR"] is None
        # Verify allowed key is present
        assert env_dump["EXPLICIT_ALLOWED_VAR"] == "safe_value"

    def test_hard_wall_clock_timeout_enforced(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_sleep", implementation_id="test_sleep")
        provenance = _make_provenance()

        # Tool attempts to sleep for 5.0 seconds, but timeout is 0.25 seconds
        caps = _make_test_capabilities(timeout_seconds=0.25)

        start = time.monotonic()
        with pytest.raises(SandboxTimeoutError) as exc_info:
            sandbox.execute(
                tool=tool,
                parameters={"seconds": 5.0},
                capabilities=caps,
                provenance=provenance,
            )
        elapsed = time.monotonic() - start

        assert "exceeded wall-clock timeout" in str(exc_info.value)
        assert exc_info.value.tool_id == "test_sleep"
        assert exc_info.value.timeout_seconds == 0.25
        # Verify process was interrupted close to the deadline, not waiting for full 5 seconds
        assert elapsed < 1.5

    def test_bounded_output_collection_kills_process_on_limit_breach(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_output_flood", implementation_id="test_output_flood")
        provenance = _make_provenance()

        # Tool attempts to emit 50 KB, but max_output_bytes is 512 bytes
        caps = _make_test_capabilities(max_output_bytes=512)

        with pytest.raises(SandboxResourceExhaustedError) as exc_info:
            sandbox.execute(
                tool=tool,
                parameters={"count": 50, "chunk": "A" * 1024},
                capabilities=caps,
                provenance=provenance,
            )

        assert "exceeded output size limit" in str(exc_info.value)
        assert exc_info.value.resource_type == "max_output_bytes"

    def test_process_group_cleanup_invariant_kills_child_and_grandchild(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_fork_and_persist", implementation_id="test_fork_and_persist")
        provenance = _make_provenance()
        caps = _make_test_capabilities(timeout_seconds=2.0)

        result = sandbox.execute(
            tool=tool,
            parameters={},
            capabilities=caps,
            provenance=provenance,
        )

        assert result.success is True
        child_pid = result.output.get("child_pid")
        assert child_pid is not None

        # Small grace period to allow OS to deliver signals and reap
        time.sleep(0.2)

        # Invariant: A sandbox execution must not return while its process group remains alive.
        # os.kill(pid, 0) checks if process is alive. If dead, raises ProcessLookupError.
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)

    def test_sanitized_error_handling_does_not_leak_paths_or_secrets(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_raise_error", implementation_id="test_raise_error")
        provenance = _make_provenance()
        caps = _make_test_capabilities()

        # Simulate exception containing absolute file paths and secrets
        raw_error_message = (
            "Failed accessing file at /Users/admin/enterprise-agent-security/secret.txt with token=SECRET_TOKEN_XYZ"
        )
        result = sandbox.execute(
            tool=tool,
            parameters={"message": raw_error_message, "error_type": "ValueError"},
            capabilities=caps,
            provenance=provenance,
        )

        assert result.success is False
        assert result.error_type == "ValueError"
        assert result.error_message is not None
        # Verify absolute paths are redacted
        assert "/Users/admin" not in result.error_message
        assert "[REDACTED_PATH]" in result.error_message
        # Verify secret token is redacted
        assert "SECRET_TOKEN_XYZ" not in result.error_message
        assert "[REDACTED]" in result.error_message

    def test_unknown_implementation_id_returns_clean_error(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="unregistered_tool", implementation_id="unregistered_tool_v99")
        provenance = _make_provenance()
        caps = _make_test_capabilities()

        result = sandbox.execute(
            tool=tool,
            parameters={},
            capabilities=caps,
            provenance=provenance,
        )

        assert result.success is False
        assert result.error_type == "ImplementationNotFoundError"
        assert "is not packaged in the sandbox runtime execution registry" in result.error_message
