"""Tests for process-level filesystem access enforcement (ADR-032).

Security Hierarchy Verification:
- Level 1: Policy Authorization (PolicyEngine)
- Level 2: Process-Level Enforcement (FilesystemSandboxGuard in ProcessToolExecutionSandbox)
- Level 3: Strong OS Isolation (Container / MicroVM Backend)

Acceptance Criteria:
✓ cwd is restricted to workspace
✓ Traversal is rejected (..)
✓ Absolute paths outside workspace are rejected
✓ Symlink escapes are detected under supported threat model
✓ allowed_subpaths are enforced
✓ Read-only capability blocks supported mutations (open w/a, mkdir, remove, rename, replace, symlink, chmod)
✓ Scratch writes are isolated and ephemeral
✓ Scratch is cleaned on success, failure, and timeout
✓ Diagnostic paths are sanitized
✓ Filesystem guard is installed before tool dispatch
"""

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from app.models.execution_capability import (
    ExecutionCapabilities,
    FilesystemCapability,
    NetworkCapability,
    ResourceLimits,
)
from app.models.runtime_context import RuntimeContext
from app.runtime.exceptions import (
    SandboxTimeoutError,
    SandboxUnavailableError,
)
from app.runtime.sandbox.filesystem import FilesystemSandboxGuard
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
        raise NotImplementedError("Sandbox must execute child runner, not in-process method")


def _make_context() -> RuntimeContext:
    return RuntimeContext(
        session_id="sess-fs-test",
        authenticated_agent="agent-fs-test",
        request_id="req-fs-test",
        user_id="user-fs-test",
        principal="principal-fs-test",
    )


def _make_caps(
    workspace_root: str,
    read_only: bool = True,
    allowed_subpaths: tuple[str, ...] = (),
    allow_temp_writes: bool = False,
    timeout_seconds: float = 5.0,
) -> ExecutionCapabilities:
    return ExecutionCapabilities(
        capability_profile_id="test-fs-profile",
        filesystem=FilesystemCapability(
            workspace_root=workspace_root,
            read_only=read_only,
            allowed_subpaths=allowed_subpaths,
            allow_temp_writes=allow_temp_writes,
        ),
        environment_variables={},
        network=NetworkCapability(),
        resources=ResourceLimits(
            max_memory_bytes=256 * 1024 * 1024,
            max_cpu_seconds=5.0,
            max_output_bytes=64 * 1024,
            wall_clock_timeout_seconds=timeout_seconds,
        ),
    )


class TestFilesystemSandboxGuardUnit:
    """Unit tests for FilesystemSandboxGuard path checking logic."""

    def test_guard_allows_reads_inside_workspace(self, tmp_path: Path) -> None:
        file_path = tmp_path / "data.txt"
        file_path.write_text("hello")

        guard = FilesystemSandboxGuard(workspace_root=tmp_path, read_only=True)
        with guard:
            # Should not raise
            guard.check_access(file_path, is_write=False)
            guard.check_access("data.txt", is_write=False)

    def test_guard_denies_reads_outside_workspace(self, tmp_path: Path) -> None:
        guard = FilesystemSandboxGuard(workspace_root=tmp_path, read_only=True)
        with guard:
            with pytest.raises(PermissionError) as exc_info:
                guard.check_access("/etc/passwd", is_write=False)
            assert "[REDACTED_PATH]" in str(exc_info.value)
            assert "/etc/passwd" not in str(exc_info.value)

    def test_guard_denies_traversal_escaping_workspace(self, tmp_path: Path) -> None:
        guard = FilesystemSandboxGuard(workspace_root=tmp_path, read_only=True)
        with guard:
            with pytest.raises(PermissionError) as exc_info:
                guard.check_access(str(tmp_path / ".." / "outside.txt"), is_write=False)
            assert "[REDACTED_PATH]" in str(exc_info.value)

    def test_guard_denies_sensitive_environment_files(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET=xyz")
        guard = FilesystemSandboxGuard(workspace_root=tmp_path, read_only=True)
        with guard:
            with pytest.raises(PermissionError) as exc_info:
                guard.check_access(env_file, is_write=False)
            assert "sensitive file" in str(exc_info.value).lower()

    def test_guard_enforces_allowed_subpaths(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        allowed_file = data_dir / "item.txt"
        allowed_file.write_text("ok")

        forbidden_file = tmp_path / "root_secret.txt"
        forbidden_file.write_text("forbidden")

        guard = FilesystemSandboxGuard(
            workspace_root=tmp_path,
            allowed_subpaths=("data",),
            read_only=True,
        )
        with guard:
            guard.check_access(allowed_file, is_write=False)
            with pytest.raises(PermissionError):
                guard.check_access(forbidden_file, is_write=False)

    def test_guard_denies_mutations_when_read_only(self, tmp_path: Path) -> None:
        target = tmp_path / "new_file.txt"
        guard = FilesystemSandboxGuard(workspace_root=tmp_path, read_only=True)
        with guard:
            with pytest.raises(PermissionError) as exc_info:
                guard.check_access(target, is_write=True)
            assert "read-only" in str(exc_info.value)

    def test_guard_allows_scratch_writes_when_enabled(self, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        scratch_file = scratch / "temp.txt"

        guard = FilesystemSandboxGuard(
            workspace_root=tmp_path,
            read_only=True,
            allow_temp_writes=True,
            scratch_dir=scratch,
        )
        with guard:
            # Scratch write allowed
            guard.check_access(scratch_file, is_write=True)
            # Workspace write still forbidden
            with pytest.raises(PermissionError):
                guard.check_access(tmp_path / "test.txt", is_write=True)


class TestProcessSandboxFilesystemEnforcement:
    """End-to-end subprocess integration tests verifying process-level filesystem access enforcement."""

    def test_cwd_is_restricted_to_workspace(self, tmp_path: Path) -> None:
        # Create a file inside workspace using relative name
        f = tmp_path / "relative_target.txt"
        f.write_text("relative content")

        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_file_op", implementation_id="test_file_op")
        context = _make_context()
        caps = _make_caps(workspace_root=str(tmp_path), read_only=True)

        result = sandbox.execute(
            tool=tool,
            parameters={"op": "open_read", "path": "relative_target.txt"},
            capabilities=caps,
            context=context,
        )

        assert result.success is True
        assert result.output == "relative content"

    def test_absolute_system_file_read_is_rejected(self, tmp_path: Path) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_file_op", implementation_id="test_file_op")
        context = _make_context()
        caps = _make_caps(workspace_root=str(tmp_path), read_only=True)

        result = sandbox.execute(
            tool=tool,
            parameters={"op": "open_read", "path": "/etc/passwd"},
            capabilities=caps,
            context=context,
        )

        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "[REDACTED_PATH]" in result.error_message
        assert "/etc/passwd" not in result.error_message

    def test_path_traversal_escaping_workspace_is_rejected(self, tmp_path: Path) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_file_op", implementation_id="test_file_op")
        context = _make_context()
        caps = _make_caps(workspace_root=str(tmp_path), read_only=True)

        result = sandbox.execute(
            tool=tool,
            parameters={"op": "open_read", "path": "../../etc/hosts"},
            capabilities=caps,
            context=context,
        )

        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "[REDACTED_PATH]" in result.error_message

    def test_symlink_escape_is_rejected(self, tmp_path: Path) -> None:
        # Create a symlink inside workspace pointing to /etc/hosts
        symlink_target = tmp_path / "sym_hosts"
        try:
            os.symlink("/etc/hosts", symlink_target)
        except OSError:
            pytest.skip("Symlink creation not supported in this test environment")

        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_file_op", implementation_id="test_file_op")
        context = _make_context()
        caps = _make_caps(workspace_root=str(tmp_path), read_only=True)

        result = sandbox.execute(
            tool=tool,
            parameters={"op": "open_read", "path": "sym_hosts"},
            capabilities=caps,
            context=context,
        )

        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "[REDACTED_PATH]" in result.error_message

    def test_allowed_subpaths_are_enforced(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "allowed_data"
        data_dir.mkdir()
        allowed_file = data_dir / "info.txt"
        allowed_file.write_text("allowed info")

        disallowed_file = tmp_path / "forbidden.txt"
        disallowed_file.write_text("forbidden info")

        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_file_op", implementation_id="test_file_op")
        context = _make_context()
        caps = _make_caps(
            workspace_root=str(tmp_path),
            read_only=True,
            allowed_subpaths=("allowed_data",),
        )

        # 1. Access within allowed subpath succeeds
        res_allowed = sandbox.execute(
            tool=tool,
            parameters={"op": "open_read", "path": str(allowed_file)},
            capabilities=caps,
            context=context,
        )
        assert res_allowed.success is True
        assert res_allowed.output == "allowed info"

        # 2. Access outside allowed subpath is rejected
        res_denied = sandbox.execute(
            tool=tool,
            parameters={"op": "open_read", "path": str(disallowed_file)},
            capabilities=caps,
            context=context,
        )
        assert res_denied.success is False
        assert res_denied.error_type == "PermissionError"
        assert "[REDACTED_PATH]" in res_denied.error_message

    @pytest.mark.parametrize(
        "op,params",
        [
            ("open_write", {"path": "test_write.txt", "content": "bad"}),
            ("open_append", {"path": "test_append.txt", "content": "bad"}),
            ("mkdir", {"path": "new_dir"}),
            ("makedirs", {"path": "nested/new_dir"}),
            ("remove", {"path": "existing.txt"}),
            ("rmdir", {"path": "empty_dir"}),
            ("rename", {"src": "existing.txt", "dst": "renamed.txt"}),
            ("replace", {"src": "existing.txt", "dst": "replaced.txt"}),
            ("symlink", {"src": "existing.txt", "dst": "symlink.txt"}),
            ("chmod", {"path": "existing.txt", "mode_int": 0o600}),
        ],
    )
    def test_read_only_capability_blocks_all_supported_mutations(
        self, tmp_path: Path, op: str, params: dict[str, Any]
    ) -> None:
        # Prepare existing files/dirs needed for mutation tests
        (tmp_path / "existing.txt").write_text("existing")
        (tmp_path / "empty_dir").mkdir(exist_ok=True)

        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_file_op", implementation_id="test_file_op")
        context = _make_context()
        caps = _make_caps(workspace_root=str(tmp_path), read_only=True)

        full_params = {"op": op, **params}
        result = sandbox.execute(
            tool=tool,
            parameters=full_params,
            capabilities=caps,
            context=context,
        )

        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "read-only" in result.error_message.lower() or "[REDACTED_PATH]" in result.error_message

    def test_scratch_writes_are_isolated_and_ephemeral(self, tmp_path: Path) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_file_op", implementation_id="test_file_op")
        context = _make_context()
        caps = _make_caps(
            workspace_root=str(tmp_path),
            read_only=True,
            allow_temp_writes=True,
        )

        result = sandbox.execute(
            tool=tool,
            parameters={"op": "scratch_write", "filename": "ephemeral_data.txt", "content": "ephemeral"},
            capabilities=caps,
            context=context,
        )

        assert result.success is True
        scratch_target = result.output["target"]
        scratch_dir = os.path.dirname(scratch_target)

        # Invariant: Ephemeral scratch directory is purged upon execution completion
        assert not os.path.exists(scratch_dir)

    def test_scratch_cleaned_up_on_tool_failure(self, tmp_path: Path) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_raise_error", implementation_id="test_raise_error")
        context = _make_context()
        caps = _make_caps(
            workspace_root=str(tmp_path),
            read_only=True,
            allow_temp_writes=True,
        )

        result = sandbox.execute(
            tool=tool,
            parameters={"message": "fail", "error_type": "ValueError"},
            capabilities=caps,
            context=context,
        )
        assert result.success is False

        # Verify any scratch directories created under /tmp or temp dir prefix are cleaned up
        temp_dir = tempfile.gettempdir()
        leftover = [
            f for f in os.listdir(temp_dir)
            if f.startswith("sandbox_scratch_") and os.path.isdir(os.path.join(temp_dir, f))
        ]
        # Any newly spawned scratch dir must have been cleaned up
        assert len(leftover) == 0

    def test_scratch_cleaned_up_on_timeout(self, tmp_path: Path) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_sleep", implementation_id="test_sleep")
        context = _make_context()
        caps = _make_caps(
            workspace_root=str(tmp_path),
            read_only=True,
            allow_temp_writes=True,
            timeout_seconds=0.25,
        )

        with pytest.raises(SandboxTimeoutError):
            sandbox.execute(
                tool=tool,
                parameters={"seconds": 5.0},
                capabilities=caps,
                context=context,
            )

        temp_dir = tempfile.gettempdir()
        leftover = [
            f for f in os.listdir(temp_dir)
            if f.startswith("sandbox_scratch_") and os.path.isdir(os.path.join(temp_dir, f))
        ]
        assert len(leftover) == 0

    def test_missing_workspace_root_fails_closed(self) -> None:
        sandbox = ProcessToolExecutionSandbox()
        tool = MockTool(tool_id="test_echo", implementation_id="test_echo")
        context = _make_context()
        caps = _make_caps(
            workspace_root="/non_existent_workspace_path_12345",
            read_only=True,
        )

        with pytest.raises(SandboxUnavailableError) as exc_info:
            sandbox.execute(
                tool=tool,
                parameters={"message": "hi"},
                capabilities=caps,
                context=context,
            )
        assert "Workspace root directory does not exist" in str(exc_info.value)
