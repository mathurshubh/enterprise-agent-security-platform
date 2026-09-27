"""Tests for ExecutionCapability and SandboxExecutionResult domain models (ADR-032)."""

import pytest
from pydantic import ValidationError

from app.models.execution_capability import (
    ExecutionCapabilities,
    FilesystemCapability,
    NetworkCapability,
    NetworkEgressMode,
    ResourceLimits,
)
from app.models.execution_grant import ExecutionGrant, GrantState
from app.models.runtime_execution_grant import RuntimeExecutionGrant
from app.models.sandbox_execution_result import SandboxExecutionResult
from app.runtime.exceptions import (
    CapabilityDigestMismatchError,
    CapabilityProfileNotFoundError,
    SandboxError,
    SandboxIsolationError,
    SandboxResourceExhaustedError,
    SandboxTimeoutError,
    SandboxUnavailableError,
)


def _make_valid_capabilities(
    profile_id: str = "test-profile-1",
    workspace_root: str = "/tmp/sandbox/session-1",
    read_only: bool = True,
    allowed_subpaths: tuple[str, ...] = ("input", "output"),
    env: dict[str, str] | None = None,
    network_mode: NetworkEgressMode = NetworkEgressMode.DISABLED,
    destinations: tuple[str, ...] = (),
    timeout_seconds: float = 10.0,
) -> ExecutionCapabilities:
    """Helper factory for valid ExecutionCapabilities."""
    if env is None:
        env = {"TOOL_LANG": "en", "DEBUG": "0"}
    return ExecutionCapabilities(
        capability_profile_id=profile_id,
        filesystem=FilesystemCapability(
            workspace_root=workspace_root,
            read_only=read_only,
            allowed_subpaths=allowed_subpaths,
            allow_temp_writes=not read_only,
        ),
        environment_variables=env,
        network=NetworkCapability(
            mode=network_mode,
            allowed_destinations=destinations,
        ),
        resources=ResourceLimits(
            max_memory_bytes=128 * 1024 * 1024,
            max_cpu_seconds=2.0,
            max_output_bytes=64 * 1024,
            wall_clock_timeout_seconds=timeout_seconds,
        ),
    )


class TestExecutionCapabilitiesImmutability:
    """Invariant 1: Frozen models prevent mutation after construction."""

    def test_execution_capabilities_is_frozen(self) -> None:
        caps = _make_valid_capabilities()
        with pytest.raises(ValidationError):
            caps.capability_profile_id = "mutated-id"  # type: ignore[misc]

    def test_filesystem_capability_is_frozen(self) -> None:
        fs = FilesystemCapability(workspace_root="/tmp/sandbox")
        with pytest.raises(ValidationError):
            fs.read_only = False  # type: ignore[misc]

    def test_network_capability_is_frozen(self) -> None:
        net = NetworkCapability(mode=NetworkEgressMode.DISABLED)
        with pytest.raises(ValidationError):
            net.mode = NetworkEgressMode.ALLOWLIST  # type: ignore[misc]

    def test_resource_limits_is_frozen(self) -> None:
        res = ResourceLimits()
        with pytest.raises(ValidationError):
            res.max_cpu_seconds = 10.0  # type: ignore[misc]

    def test_environment_variables_mapping_is_immutable(self) -> None:
        caps = _make_valid_capabilities(env={"KEY": "VAL"})
        with pytest.raises(TypeError):
            caps.environment_variables["KEY"] = "NEW_VAL"  # type: ignore[index]


class TestDeterministicCapabilityDigest:
    """Invariant 2: Same semantic capability set yields identical SHA-256 digest regardless of collection ordering."""

    def test_identical_capabilities_produce_identical_digest(self) -> None:
        caps_a = _make_valid_capabilities()
        caps_b = _make_valid_capabilities()
        assert caps_a.compute_digest() == caps_b.compute_digest()
        assert len(caps_a.compute_digest()) == 64

    def test_destination_ordering_does_not_change_digest(self) -> None:
        caps_1 = _make_valid_capabilities(
            network_mode=NetworkEgressMode.ALLOWLIST,
            destinations=("api.example.com:443", "auth.internal:8443"),
        )
        caps_2 = _make_valid_capabilities(
            network_mode=NetworkEgressMode.ALLOWLIST,
            destinations=("auth.internal:8443", "api.example.com:443"),
        )
        assert caps_1.compute_digest() == caps_2.compute_digest()

    def test_subpaths_ordering_does_not_change_digest(self) -> None:
        caps_1 = _make_valid_capabilities(allowed_subpaths=("data/sub2", "data/sub1"))
        caps_2 = _make_valid_capabilities(allowed_subpaths=("data/sub1", "data/sub2"))
        assert caps_1.compute_digest() == caps_2.compute_digest()

    def test_environment_variable_ordering_does_not_change_digest(self) -> None:
        caps_1 = _make_valid_capabilities(env={"A": "1", "B": "2", "C": "3"})
        caps_2 = _make_valid_capabilities(env={"C": "3", "A": "1", "B": "2"})
        assert caps_1.compute_digest() == caps_2.compute_digest()

    def test_different_capabilities_produce_different_digest(self) -> None:
        base = _make_valid_capabilities(timeout_seconds=10.0)
        altered_timeout = _make_valid_capabilities(timeout_seconds=15.0)
        altered_workspace = _make_valid_capabilities(workspace_root="/tmp/other-workspace")
        altered_env = _make_valid_capabilities(env={"TOOL_LANG": "fr"})

        assert base.compute_digest() != altered_timeout.compute_digest()
        assert base.compute_digest() != altered_workspace.compute_digest()
        assert base.compute_digest() != altered_env.compute_digest()


class TestNetworkDefaultDenyAndValidation:
    """Invariant 3: Network defaults to DISABLED with zero destinations; ALLOWLIST requires destinations."""

    def test_default_network_is_disabled_with_empty_destinations(self) -> None:
        net = NetworkCapability()
        assert net.mode == NetworkEgressMode.DISABLED
        assert net.allowed_destinations == ()

    def test_disabled_mode_with_destinations_fails_closed(self) -> None:
        with pytest.raises(ValidationError, match="allowed_destinations must be empty"):
            NetworkCapability(
                mode=NetworkEgressMode.DISABLED,
                allowed_destinations=("api.github.com:443",),
            )

    def test_allowlist_mode_without_destinations_fails_closed(self) -> None:
        with pytest.raises(ValidationError, match="must contain at least one destination"):
            NetworkCapability(
                mode=NetworkEgressMode.ALLOWLIST,
                allowed_destinations=(),
            )

    def test_valid_allowlist_destinations_accepted(self) -> None:
        net = NetworkCapability(
            mode=NetworkEgressMode.ALLOWLIST,
            allowed_destinations=("api.internal:8080", "10.0.0.1:443"),
        )
        assert len(net.allowed_destinations) == 2

    @pytest.mark.parametrize(
        "invalid_dest",
        [
            "invalid-no-port",
            ":443",
            "api.example.com:",
            "api.example.com:not-a-port",
            "api.example.com:0",
            "api.example.com:65536",
            "api.example.com: 443",
            "api.example.com:443\x00",
        ],
    )
    def test_invalid_destination_syntax_rejected(self, invalid_dest: str) -> None:
        with pytest.raises(ValidationError):
            NetworkCapability(
                mode=NetworkEgressMode.ALLOWLIST,
                allowed_destinations=(invalid_dest,),
            )


class TestFilesystemConfinementValidation:
    """Invariant 4: workspace_root must be absolute/canonical; traversal and null bytes rejected."""

    def test_absolute_workspace_root_accepted_and_resolved(self) -> None:
        fs = FilesystemCapability(workspace_root="/tmp/sandbox")
        assert fs.workspace_root.startswith("/")

    def test_relative_workspace_root_rejected(self) -> None:
        with pytest.raises(ValidationError, match="workspace_root must be an absolute path"):
            FilesystemCapability(workspace_root="relative/path/sandbox")

    def test_null_bytes_in_workspace_root_rejected(self) -> None:
        with pytest.raises(ValidationError, match="null bytes"):
            FilesystemCapability(workspace_root="/tmp/sandbox\x00/root")

    def test_subpaths_with_path_traversal_rejected(self) -> None:
        with pytest.raises(ValidationError, match="traversal elements"):
            FilesystemCapability(
                workspace_root="/tmp/sandbox",
                allowed_subpaths=("data", "../escape"),
            )

    def test_subpaths_with_absolute_path_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be relative to workspace_root"):
            FilesystemCapability(
                workspace_root="/tmp/sandbox",
                allowed_subpaths=("/etc/passwd",),
            )


class TestResourceBoundsValidation:
    """Invariant 5: Resource limits enforce positive values and explicit upper bounds."""

    def test_valid_default_resource_limits(self) -> None:
        res = ResourceLimits()
        assert res.max_memory_bytes == 256 * 1024 * 1024
        assert res.max_cpu_seconds == 5.0
        assert res.max_output_bytes == 1024 * 1024
        assert res.wall_clock_timeout_seconds == 10.0

    @pytest.mark.parametrize(
        ("mem", "cpu", "out", "timeout"),
        [
            (0, 5.0, 1000, 10.0),  # mem must be > 0
            (-1, 5.0, 1000, 10.0),
            (1024, 0.0, 1000, 10.0),  # cpu must be > 0
            (1024, -1.0, 1000, 10.0),
            (1024, 5.0, -1, 10.0),  # out must be >= 0
            (1024, 5.0, 1000, 0.0),  # timeout must be > 0
            (1024, 5.0, 1000, -1.0),
            (5 * 1024 * 1024 * 1024, 5.0, 1000, 10.0),  # mem > 4GB max
            (1024, 301.0, 1000, 10.0),  # cpu > 300s max
            (1024, 5.0, 1000, 601.0),  # timeout > 600s max
        ],
    )
    def test_resource_limits_boundary_violations_rejected(
        self, mem: int, cpu: float, out: int, timeout: float
    ) -> None:
        with pytest.raises(ValidationError):
            ResourceLimits(
                max_memory_bytes=mem,
                max_cpu_seconds=cpu,
                max_output_bytes=out,
                wall_clock_timeout_seconds=timeout,
            )


class TestEnvironmentAllowlistAndSecretScrubbing:
    """Invariant 6: Environment variables treat input as allowlist and block platform secrets."""

    @pytest.mark.parametrize(
        "secret_key",
        [
            "POSTGRES_URL",
            "postgres_url",
            "JWT_SECRET_KEY",
            "jwt_secret_key",
            "DATABASE_URL",
            "SECRET_KEY",
            "AWS_SECRET_ACCESS_KEY",
            "API_KEY",
            "OPENAI_API_KEY",
            "APP_PASSWORD",
        ],
    )
    def test_platform_secrets_in_env_allowlist_rejected(self, secret_key: str) -> None:
        with pytest.raises(ValidationError, match="Platform secret or dangerous key"):
            _make_valid_capabilities(env={secret_key: "leaked_value"})

    def test_null_bytes_in_env_rejected(self) -> None:
        with pytest.raises(ValidationError, match="null bytes"):
            _make_valid_capabilities(env={"SAFE_KEY\x00": "val"})


class TestSandboxExecutionResultAndExceptions:
    """Invariant 7: SandboxExecutionResult and domain exceptions are correctly structured."""

    def test_sandbox_execution_result_immutability(self) -> None:
        res = SandboxExecutionResult(
            success=True,
            output="hello world",
            output_digest="digest-123",
            exit_code=0,
            duration_ms=45,
            resource_usage={"memory_bytes": 1024},
        )
        assert res.success is True
        assert res.exit_code == 0
        assert res.duration_ms == 45
        with pytest.raises(ValidationError):
            res.success = False  # type: ignore[misc]

    def test_sandbox_exceptions_hierarchy(self) -> None:
        assert issubclass(SandboxUnavailableError, SandboxError)
        assert issubclass(SandboxTimeoutError, SandboxError)
        assert issubclass(SandboxResourceExhaustedError, SandboxError)
        assert issubclass(SandboxIsolationError, SandboxError)
        assert issubclass(CapabilityDigestMismatchError, SandboxError)
        assert issubclass(CapabilityProfileNotFoundError, SandboxError)

        timeout_err = SandboxTimeoutError("Tool timed out", tool_id="read_file", timeout_seconds=5.0)
        assert timeout_err.tool_id == "read_file"
        assert timeout_err.timeout_seconds == 5.0

        mismatch_err = CapabilityDigestMismatchError(
            "Digest mismatch", expected_digest="exp-1", actual_digest="act-2", tool_id="tool-1"
        )
        assert mismatch_err.expected_digest == "exp-1"
        assert mismatch_err.actual_digest == "act-2"


class TestExecutionGrantIntegration:
    """Invariant 8: ExecutionGrant integrates capability references preserving state machine."""

    def test_execution_grant_accepts_capability_reference_and_digest(self) -> None:
        from datetime import datetime, timezone

        grant = ExecutionGrant(
            grant_id="grant-101",
            session_id="session-1",
            agent_id="agent-1",
            tool_id="file_read",
            execution_parameters={"path": "report.txt"},
            originating_audit_event_id="audit-1",
            risk_score=0,
            required_response="ALLOW",
            enforcement_epoch=1,
            state=GrantState.APPROVED,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            capability_profile_id="profile-default-fs",
            capability_digest="abc123digest",
        )
        assert grant.capability_profile_id == "profile-default-fs"
        assert grant.capability_digest == "abc123digest"

        # Verify deepcopy retains capability reference
        import copy

        copied = copy.deepcopy(grant)
        assert copied.capability_profile_id == "profile-default-fs"
        assert copied.capability_digest == "abc123digest"

    def test_runtime_execution_grant_accepts_capability_reference(self) -> None:
        from app.models.audit_event import Decision
        from app.models.execution_binding import ExecutionBinding

        binding = ExecutionBinding.from_operation(tool_id="file_read", parameters={"path": "a.txt"})
        grant = RuntimeExecutionGrant(
            grant_id="grant-r-1",
            authority_id="auth-1",
            agent_id="agent-1",
            session_id="session-1",
            decision=Decision.ALLOW,
            binding=binding,
            issued_at=100.0,
            expires_at=120.0,
            signature="sig-1",
            capability_profile_id="profile-default-fs",
            capability_digest="abc123digest",
        )
        assert grant.capability_profile_id == "profile-default-fs"
        assert grant.capability_digest == "abc123digest"
