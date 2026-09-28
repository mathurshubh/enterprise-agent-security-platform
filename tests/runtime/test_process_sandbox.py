"""Tests for ProcessToolExecutionSandbox subprocess isolation and cleanup (ADR-032)."""

import os
import time
from pathlib import Path
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
    SandboxUnavailableError,
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
    workspace_root: str = "/tmp",
    required_controls: tuple[str, ...] = (),
) -> ExecutionCapabilities:
    return ExecutionCapabilities(
        capability_profile_id="test-sandbox-profile",
        filesystem=FilesystemCapability(
            workspace_root=workspace_root,
            read_only=True,
        ),
        environment_variables=env or {},
        network=NetworkCapability(),
        resources=ResourceLimits(
            max_memory_bytes=256 * 1024 * 1024,
            max_cpu_seconds=5.0,
            max_output_bytes=max_output_bytes,
            wall_clock_timeout_seconds=timeout_seconds,
            required_controls=required_controls,
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
        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
        assert isinstance(sandbox, ToolExecutionSandboxProtocol)


class TestProcessSandboxExecution:
    """Verifies execution, clean environment, timeouts, and bounded output."""

    def test_successful_tool_execution(self) -> None:
        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
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

        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
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

        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
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
        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
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
        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
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
        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
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
        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
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
        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
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


class TestTrustedRunnerBootstrap:
    """The workspace must not decide which code becomes the sandbox runner.

    The child is launched as ``python -m app.runtime.sandbox.runner`` with the working
    directory pinned to the execution workspace. With ``-m``, CPython prepends the
    working directory to ``sys.path`` ahead of ``PYTHONPATH`` — so a workspace holding
    ``app/runtime/sandbox/runner.py`` was imported *as* the runner, and
    workspace-controlled code executed as the sandbox bootstrap.

    The ordering is what makes this serious: that code runs before the filesystem and
    network guards are installed, so no check inside the runner can defend against it.
    """

    @staticmethod
    def _plant_shadow_runner(workspace: Path) -> Path:
        """Create a workspace package that would shadow the trusted runner."""
        marker = workspace / "SHADOW_RUNNER_EXECUTED"
        package = workspace / "app" / "runtime" / "sandbox"
        package.mkdir(parents=True, exist_ok=True)
        for directory in (
            workspace / "app",
            workspace / "app" / "runtime",
            package,
        ):
            (directory / "__init__.py").write_text("", encoding="utf-8")
        (package / "runner.py").write_text(
            "import pathlib\n"
            f"pathlib.Path({str(marker)!r}).write_text('shadow runner executed')\n",
            encoding="utf-8",
        )
        return marker

    @pytest.mark.security_invariant
    def test_a_workspace_cannot_shadow_the_trusted_runner(self, tmp_path: Path) -> None:
        """Asserted against a workspace that actively attempts the shadowing.

        A test that merely exercises a benign workspace would pass against the
        vulnerable implementation, so the shadow package is planted deliberately and its
        marker must never appear.
        """
        marker = self._plant_shadow_runner(tmp_path)
        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
        tool = MockTool(tool_id="test_echo", implementation_id="test_echo")

        result = sandbox.execute(
            tool=tool,
            parameters={"message": "trusted"},
            capabilities=_make_test_capabilities(workspace_root=str(tmp_path)),
            provenance=_make_provenance(),
        )

        assert not marker.exists(), (
            "workspace-controlled code executed as the sandbox runner"
        )
        assert result.success is True, "the trusted runner handled the execution"
        assert result.output == "trusted"

    @pytest.mark.security_invariant
    def test_the_trusted_runner_is_resolved_independently_of_the_workspace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The launch must not place the workspace on the child's import path.

        Asserted on the argv the sandbox builds, because the defence has to operate at
        launch: by the time any code inside the child could inspect ``sys.path``, the
        shadowing import has already happened.
        """
        import app.runtime.sandbox.process_sandbox as module

        captured: dict[str, object] = {}
        real_popen = module.subprocess.Popen

        def _capturing_popen(argv, **kwargs):
            captured["argv"] = list(argv)
            captured["cwd"] = kwargs.get("cwd")
            captured["env"] = dict(kwargs.get("env") or {})
            return real_popen(argv, **kwargs)

        monkeypatch.setattr(module.subprocess, "Popen", _capturing_popen)

        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
        tool = MockTool(tool_id="test_echo", implementation_id="test_echo")
        sandbox.execute(
            tool=tool,
            parameters={"message": "hi"},
            capabilities=_make_test_capabilities(workspace_root=str(tmp_path)),
            provenance=_make_provenance(),
        )

        argv = captured["argv"]
        assert "-P" in argv, (
            "the child must not prepend its working directory to sys.path"
        )
        assert argv.index("-P") < argv.index("-m"), "-P must precede module resolution"
        assert captured["cwd"] == str(tmp_path), (
            "the workspace remains the working directory for containment"
        )
        assert captured["env"].get("PYTHONPATH"), (
            "the trusted package is resolved through PYTHONPATH"
        )


class TestResourceControlsFailClosed:
    """A configured resource control is an execution precondition.

    The prior implementation attempted both limits inside one ``try`` and swallowed
    every failure, which produced two defects: a control could be unestablished while
    the platform behaved as though it were enforced, and because memory was attempted
    first, its failure meant the CPU limit was never attempted at all.

    Every control now receives an explicit outcome — ENFORCED, UNSUPPORTED or FAILED.
    There is no state in which a control is neither established nor reported.
    """

    @staticmethod
    def _clear_cache() -> None:
        from app.runtime.sandbox import resource_controls

        resource_controls._assessment_cache.clear()

    def test_each_control_receives_an_explicit_outcome(self) -> None:
        from app.runtime.sandbox.resource_controls import (
            ResourceControlOutcome,
            assess_resource_controls,
        )

        self._clear_cache()
        assessments = assess_resource_controls(256 * 1024 * 1024, 5.0)

        assert {a.control for a in assessments} == {"memory", "cpu"}
        for assessment in assessments:
            assert isinstance(assessment.outcome, ResourceControlOutcome)
            if not assessment.established:
                assert assessment.detail, "an unestablished control must say why"

    @pytest.mark.security_invariant
    def test_a_required_control_that_cannot_be_established_refuses_the_launch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Required + unestablishable must not start the workload."""
        import app.runtime.sandbox.process_sandbox as module
        from app.runtime.sandbox.resource_controls import (
            ResourceControlAssessment,
            ResourceControlOutcome,
        )

        monkeypatch.setattr(
            module,
            "assess_resource_controls",
            lambda mem, cpu: (
                ResourceControlAssessment(
                    "memory", ResourceControlOutcome.UNSUPPORTED, "probe says no"
                ),
                ResourceControlAssessment("cpu", ResourceControlOutcome.ENFORCED),
            ),
        )
        launched: list[object] = []
        real_popen = module.subprocess.Popen
        monkeypatch.setattr(
            module.subprocess,
            "Popen",
            lambda *a, **k: (launched.append(a), real_popen(*a, **k))[1],
        )

        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
        tool = MockTool(tool_id="test_echo", implementation_id="test_echo")
        caps = _make_test_capabilities(
            workspace_root=str(tmp_path), required_controls=("memory",)
        )

        with pytest.raises(SandboxUnavailableError, match="could not be established"):
            sandbox.execute(
                tool=tool,
                parameters={"message": "hi"},
                capabilities=caps,
                provenance=_make_provenance(),
            )

        assert launched == [], "no child process may be started"

    @pytest.mark.security_invariant
    def test_a_control_that_fails_refuses_even_when_not_required(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """'Optional' means the platform may operate without the control, not that a
        failure while establishing it may be ignored."""
        import app.runtime.sandbox.process_sandbox as module
        from app.runtime.sandbox.resource_controls import (
            ResourceControlAssessment,
            ResourceControlOutcome,
        )

        monkeypatch.setattr(
            module,
            "assess_resource_controls",
            lambda mem, cpu: (
                ResourceControlAssessment("memory", ResourceControlOutcome.ENFORCED),
                ResourceControlAssessment(
                    "cpu", ResourceControlOutcome.FAILED, "setrlimit refused"
                ),
            ),
        )
        launched: list[object] = []
        real_popen = module.subprocess.Popen
        monkeypatch.setattr(
            module.subprocess,
            "Popen",
            lambda *a, **k: (launched.append(a), real_popen(*a, **k))[1],
        )

        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
        tool = MockTool(tool_id="test_echo", implementation_id="test_echo")

        with pytest.raises(SandboxUnavailableError, match="cpu=FAILED"):
            sandbox.execute(
                tool=tool,
                parameters={"message": "hi"},
                capabilities=_make_test_capabilities(workspace_root=str(tmp_path)),
                provenance=_make_provenance(),
            )

        assert launched == [], "a failed control must not start the workload"

    @pytest.mark.security_invariant
    def test_an_unsupported_optional_control_executes_explicitly_degraded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The dangerous state is not that a control is unavailable; it is behaving as
        though it were enforced. Degraded execution is permitted and surfaced."""
        import app.runtime.sandbox.process_sandbox as module
        from app.runtime.sandbox.resource_controls import (
            ResourceControlAssessment,
            ResourceControlOutcome,
        )

        monkeypatch.setattr(
            module,
            "assess_resource_controls",
            lambda mem, cpu: (
                ResourceControlAssessment(
                    "memory", ResourceControlOutcome.UNSUPPORTED, "no useful ceiling"
                ),
                ResourceControlAssessment("cpu", ResourceControlOutcome.ENFORCED),
            ),
        )
        warnings: list[str] = []
        monkeypatch.setattr(
            module.logger,
            "warning",
            lambda msg, *args: warnings.append(msg % args if args else msg),
        )

        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
        tool = MockTool(tool_id="test_echo", implementation_id="test_echo")

        result = sandbox.execute(
            tool=tool,
            parameters={"message": "degraded"},
            capabilities=_make_test_capabilities(workspace_root=str(tmp_path)),
            provenance=_make_provenance(),
        )

        assert result.success is True
        assert len(warnings) == 1
        assert "memory=UNSUPPORTED" in warnings[0], (
            "the missing control must be surfaced, never silently omitted"
        )

    def test_a_memory_failure_does_not_suppress_the_cpu_attempt(self) -> None:
        """The second defect: memory was attempted first inside a shared try, so its
        failure meant the CPU limit was never attempted at all."""
        import resource as resource_module

        from app.runtime.sandbox.resource_controls import apply_resource_controls

        attempted: list[int] = []
        original = resource_module.setrlimit

        def _recording(rid, limits):
            attempted.append(rid)
            if rid == resource_module.RLIMIT_AS:
                raise ValueError("memory refused")
            return original(rid, limits)

        resource_module.setrlimit = _recording
        try:
            with pytest.raises(RuntimeError, match="memory"):
                apply_resource_controls(256 * 1024 * 1024, 5.0)
        finally:
            resource_module.setrlimit = original

        assert resource_module.RLIMIT_CPU in attempted, (
            "the CPU control must be attempted even after the memory control fails"
        )

    def test_establishment_failure_in_the_child_aborts_the_launch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defence in depth behind the gate: a preexec failure prevents exec, so the
        workload never runs even if the assessment were wrong."""
        import app.runtime.sandbox.process_sandbox as module

        monkeypatch.setattr(
            module,
            "apply_resource_controls",
            lambda mem, cpu: (_ for _ in ()).throw(RuntimeError("forced failure")),
        )

        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
        tool = MockTool(tool_id="test_echo", implementation_id="test_echo")

        with pytest.raises(SandboxUnavailableError):
            sandbox.execute(
                tool=tool,
                parameters={"message": "hi"},
                capabilities=_make_test_capabilities(workspace_root=str(tmp_path)),
                provenance=_make_provenance(),
            )

    def test_all_establishable_controls_permit_a_normal_launch(
        self, tmp_path: Path
    ) -> None:
        """The gate must not refuse the ordinary case."""
        sandbox = ProcessToolExecutionSandbox(enable_testing_handlers=True)
        tool = MockTool(tool_id="test_echo", implementation_id="test_echo")

        result = sandbox.execute(
            tool=tool,
            parameters={"message": "ok"},
            capabilities=_make_test_capabilities(workspace_root=str(tmp_path)),
            provenance=_make_provenance(),
        )

        assert result.success is True
        assert result.output == "ok"
