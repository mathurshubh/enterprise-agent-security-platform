"""Tests for ToolExecutionSandboxProtocol, CapabilityProfileRegistry, and binding verification (ADR-032)."""

from collections.abc import Mapping
from typing import Any

import pytest

from app.models.execution_capability import (
    ExecutionCapabilities,
    FilesystemCapability,
    NetworkCapability,
    ResourceLimits,
)
from app.models.execution_grant import ExecutionGrant, GrantState
from app.models.execution_provenance import ExecutionProvenance
from app.models.sandbox_execution_result import SandboxExecutionResult
from app.runtime.capability_registry import (
    InMemoryCapabilityProfileRegistry,
    verify_capability_binding,
)
from app.runtime.contracts import (
    CapabilityProfileRegistryProtocol,
    ToolExecutionSandboxProtocol,
)
from app.runtime.exceptions import (
    CapabilityDigestMismatchError,
    CapabilityProfileNotFoundError,
)
from app.tools.base_tool import BaseTool


def _make_sample_capabilities(profile_id: str = "profile-fs-1") -> ExecutionCapabilities:
    return ExecutionCapabilities(
        capability_profile_id=profile_id,
        filesystem=FilesystemCapability(
            workspace_root="/tmp/sandbox/session-1",
            read_only=True,
        ),
        environment_variables={"TOOL_VAR": "1"},
        network=NetworkCapability(),
        resources=ResourceLimits(
            max_memory_bytes=128 * 1024 * 1024,
            max_cpu_seconds=2.0,
            max_output_bytes=32 * 1024,
            wall_clock_timeout_seconds=5.0,
        ),
    )


class StubValidSandbox:
    """Stub implementation conforming to ToolExecutionSandboxProtocol."""

    def execute(
        self,
        *,
        tool: BaseTool,
        parameters: Mapping[str, Any],
        capabilities: ExecutionCapabilities,
        provenance: ExecutionProvenance,

        implementation_id: str | None = None,

        tool_version: str | None = None,
    ) -> SandboxExecutionResult:
        return SandboxExecutionResult(
            success=True,
            output="mock output",
            output_digest="mock-digest",
            exit_code=0,
            duration_ms=10,
        )


class StubNonConformingSandbox:
    """Class missing the execute method."""

    def run(self, tool: Any) -> None:
        pass


class TestToolExecutionSandboxProtocol:
    """Tests verifying ToolExecutionSandboxProtocol runtime checkability."""

    def test_conforming_sandbox_satisfies_protocol(self) -> None:
        sandbox = StubValidSandbox()
        assert isinstance(sandbox, ToolExecutionSandboxProtocol)

    def test_non_conforming_sandbox_fails_protocol(self) -> None:
        invalid = StubNonConformingSandbox()
        assert not isinstance(invalid, ToolExecutionSandboxProtocol)


class TestCapabilityProfileRegistryProtocol:
    """Tests verifying CapabilityProfileRegistryProtocol and InMemoryCapabilityProfileRegistry."""

    def test_in_memory_registry_satisfies_protocol(self) -> None:
        registry = InMemoryCapabilityProfileRegistry()
        assert isinstance(registry, CapabilityProfileRegistryProtocol)

    def test_register_and_resolve_profile(self) -> None:
        registry = InMemoryCapabilityProfileRegistry()
        caps = _make_sample_capabilities("profile-alpha")

        assert not registry.exists("profile-alpha")
        registry.register_profile(caps)
        assert registry.exists("profile-alpha")

        resolved = registry.resolve_profile("profile-alpha")
        assert resolved == caps
        assert resolved.capability_profile_id == "profile-alpha"
        assert len(registry.list_profiles()) == 1

    def test_resolve_unregistered_profile_raises_not_found(self) -> None:
        registry = InMemoryCapabilityProfileRegistry()
        with pytest.raises(CapabilityProfileNotFoundError, match="is not registered"):
            registry.resolve_profile("non-existent-profile")


class TestCapabilityBindingVerification:
    """Tests for verify_capability_binding invariant enforcement (ADR-032)."""

    def test_matching_grant_binding_passes(self) -> None:
        caps = _make_sample_capabilities("profile-alpha")
        digest = caps.compute_digest()

        from datetime import datetime, timezone

        grant = ExecutionGrant(
            grant_id="grant-1",
            session_id="session-1",
            agent_id="agent-1",
            tool_id="file_read",
            execution_parameters={"path": "test.txt"},
            originating_audit_event_id="audit-1",
            risk_score=0,
            required_response="ALLOW",
            enforcement_epoch=1,
            state=GrantState.APPROVED,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            capability_profile_id="profile-alpha",
            capability_digest=digest,
        )

        # Must not raise
        verify_capability_binding(grant, caps, tool_id="file_read")

    def test_profile_id_mismatch_fails_closed(self) -> None:
        caps = _make_sample_capabilities("profile-actual")
        digest = caps.compute_digest()

        from datetime import datetime, timezone

        grant = ExecutionGrant(
            grant_id="grant-1",
            session_id="session-1",
            agent_id="agent-1",
            tool_id="file_read",
            execution_parameters={},
            originating_audit_event_id="audit-1",
            risk_score=0,
            required_response="ALLOW",
            enforcement_epoch=1,
            state=GrantState.APPROVED,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            capability_profile_id="profile-expected",
            capability_digest=digest,
        )

        with pytest.raises(CapabilityDigestMismatchError, match="Capability profile mismatch"):
            verify_capability_binding(grant, caps, tool_id="file_read")

    def test_capability_digest_mismatch_fails_closed(self) -> None:
        caps = _make_sample_capabilities("profile-alpha")
        # Intentionally tamper with expected digest
        tampered_digest = "0" * 64

        from datetime import datetime, timezone

        grant = ExecutionGrant(
            grant_id="grant-1",
            session_id="session-1",
            agent_id="agent-1",
            tool_id="file_read",
            execution_parameters={},
            originating_audit_event_id="audit-1",
            risk_score=0,
            required_response="ALLOW",
            enforcement_epoch=1,
            state=GrantState.APPROVED,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            capability_profile_id="profile-alpha",
            capability_digest=tampered_digest,
        )

        with pytest.raises(CapabilityDigestMismatchError) as exc_info:
            verify_capability_binding(grant, caps, tool_id="file_read")

        assert exc_info.value.expected_digest == tampered_digest
        assert exc_info.value.actual_digest == caps.compute_digest()
        assert exc_info.value.tool_id == "file_read"

    def test_grant_without_capability_fields_fails_closed(self) -> None:
        """An unbound grant is refused rather than accepted (F-008, v0.17.1).

        This previously passed deliberately, for backwards compatibility with grants
        carrying no capability fields. But a capability binding verification that accepts
        "no binding" verifies nothing: the profile comparison was conditional on the
        grant specifying a profile, so the one grant that most needed checking was the
        one that skipped the check.

        The executor refuses a profile-less grant upstream, so this was unreachable in
        production. It is fixed in the helper so any other caller inherits the same
        fail-closed answer. ADR-031 note: a persisted ExecutionGrant with no capability
        fields is consequently not executable, which is intended — it has no capability
        binding to enforce.
        """
        caps = _make_sample_capabilities("profile-alpha")

        from datetime import datetime, timezone

        grant = ExecutionGrant(
            grant_id="grant-legacy",
            session_id="session-1",
            agent_id="agent-1",
            tool_id="file_read",
            execution_parameters={},
            originating_audit_event_id="audit-1",
            risk_score=0,
            required_response="ALLOW",
            enforcement_epoch=1,
            state=GrantState.APPROVED,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            # capability_profile_id and capability_digest are None
        )

        with pytest.raises(CapabilityProfileNotFoundError, match="no capability profile"):
            verify_capability_binding(grant, caps, tool_id="file_read")

    def test_grant_with_a_profile_but_no_digest_fails_closed(self) -> None:
        """The digest half of the same fail-open (v0.17.2 Step 1).

        The digest comparison was conditional on the grant presenting a digest, so a
        profile-bound grant carrying none was admitted with its binding never verified.
        Symmetric with the profile check above: a binding that cannot be compared is
        not a verified binding.
        """
        caps = _make_sample_capabilities("profile-alpha")

        from datetime import datetime, timezone

        grant = ExecutionGrant(
            grant_id="grant-no-digest",
            session_id="session-1",
            agent_id="agent-1",
            tool_id="file_read",
            execution_parameters={},
            originating_audit_event_id="audit-1",
            risk_score=0,
            required_response="ALLOW",
            enforcement_epoch=1,
            state=GrantState.APPROVED,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            capability_profile_id="profile-alpha",
            # capability_digest deliberately absent
        )

        with pytest.raises(CapabilityDigestMismatchError, match="no capability digest"):
            verify_capability_binding(grant, caps, tool_id="file_read")
