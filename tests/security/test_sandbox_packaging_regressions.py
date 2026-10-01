"""The child runtime's registry is an explicit packaging boundary.

``SandboxExecutionRegistry`` exists so that only deliberately packaged
implementations can execute inside the sandbox. The production registry, which is
what the child runner resolves against, additionally contained nine
isolation-verification probes:

    test_file_op      open/write/mkdir/remove/rename/symlink/chmod/listdir on
                      request-supplied paths
    test_network_op   tcp_connect / udp_send / http_get / unix_connect / bind_listener
    test_env_dump     returns arbitrary os.environ values by key
    test_fork_and_persist  spawns a detached grandchild

Nothing reachable from a request could resolve them: ``implementation_id`` is
derived from registered tool objects, either from an explicit attribute or as
``f"{tool_id}_v1"``, and the probes are registered under bare names. So this was
never a remote exploit — it was a packaging boundary that did not hold, and the
reachability argument depends entirely on no surface letting a caller influence
``implementation_id``. A tool-registration API, a plugin loader or an MCP adapter
would each end that, and v0.18 plausibly introduces one.

The invariant is therefore about the boundary, not about current reachability: the
production registry contains production implementations only, and the probes are
registered solely on explicit opt-in.
"""

import pytest

from app.runtime.sandbox.registry import (
    create_default_execution_registry,
    default_execution_registry,
)
from app.runtime.sandbox.testing_registry import register_testing_handlers

PRODUCTION_IMPLEMENTATIONS = frozenset({"file_read_v1", "directory_list_v1"})

PROBE_IMPLEMENTATIONS = frozenset(
    {
        "test_getpid",
        "test_echo",
        "test_sleep",
        "test_env_dump",
        "test_output_flood",
        "test_fork_and_persist",
        "test_raise_error",
        "test_file_op",
        "test_network_op",
    }
)


@pytest.mark.security_invariant
def test_invariant_the_production_registry_packages_production_implementations_only() -> None:
    registry = create_default_execution_registry()

    for implementation_id in PRODUCTION_IMPLEMENTATIONS:
        assert registry.has_implementation(implementation_id), implementation_id

    for implementation_id in PROBE_IMPLEMENTATIONS:
        assert not registry.has_implementation(implementation_id), (
            f"'{implementation_id}' is an isolation probe and must not be packaged "
            "in the production child registry"
        )


@pytest.mark.security_invariant
def test_invariant_the_module_level_default_registry_carries_no_probes() -> None:
    """The runner resolves against this exact object, not a fresh factory result."""
    for implementation_id in PROBE_IMPLEMENTATIONS:
        assert not default_execution_registry.has_implementation(implementation_id), implementation_id


@pytest.mark.security_invariant
def test_invariant_a_probe_cannot_execute_in_a_sandbox_without_explicit_opt_in(
    tmp_path,
) -> None:
    """End to end through a real child process.

    ``test_file_op`` is the probe with the widest reach — arbitrary filesystem
    operations on request-supplied paths. A default sandbox must not be able to run it.
    """
    from app.models.execution_capability import (
        ExecutionCapabilities,
        FilesystemCapability,
        NetworkCapability,
        ResourceLimits,
    )
    from app.models.execution_provenance import ExecutionProvenance
    from app.models.tool_capability import ToolCapability
    from app.models.tool_governance import ToolGovernance
    from app.models.tool_identity import ToolIdentity
    from app.models.tool_metadata import ToolMetadata
    from app.models.tool_operational import ToolOperational
    from app.models.tool_risk_level import ToolRiskLevel
    from app.runtime.sandbox.process_sandbox import ProcessToolExecutionSandbox
    from app.tools.base_tool import BaseTool

    class _ProbeTool(BaseTool):
        implementation_id = "test_file_op"

        def __init__(self) -> None:
            self._metadata = ToolMetadata(
                identity=ToolIdentity(
                    tool_id="test_file_op",
                    name="Probe",
                    version="1.0.0",
                    description="Isolation probe",
                ),
                governance=ToolGovernance(risk_level=ToolRiskLevel.LOW),
                capability=ToolCapability(category="test"),
                operational=ToolOperational(),
            )

        @property
        def metadata(self) -> ToolMetadata:
            return self._metadata

        def execute(self, parameters: dict[str, object]) -> dict[str, object]:
            return {}

    capabilities = ExecutionCapabilities(
        capability_profile_id="profile-probe",
        filesystem=FilesystemCapability(
            workspace_root=str(tmp_path), read_only=False
        ),
        environment_variables={},
        network=NetworkCapability(),
        resources=ResourceLimits(wall_clock_timeout_seconds=10.0),
    )
    provenance = ExecutionProvenance(
        grant_id="grant-1",
        agent_id="agent-1",
        session_id="session-1",
        request_id="req-1",
        tool_id="test_file_op",
        tool_version="1.0.0",
        implementation_id="test_file_op",
    )

    default_sandbox = ProcessToolExecutionSandbox()
    refused = default_sandbox.execute(
        tool=_ProbeTool(),
        implementation_id="test_file_op",
        parameters={"op": "mkdir", "path": str(tmp_path / "created")},
        capabilities=capabilities,
        provenance=provenance,
    )

    assert refused.success is False
    assert not (tmp_path / "created").exists(), "the probe must not have run"

    opted_in = ProcessToolExecutionSandbox(enable_testing_handlers=True)
    permitted = opted_in.execute(
        tool=_ProbeTool(),
        implementation_id="test_file_op",
        parameters={"op": "mkdir", "path": str(tmp_path / "created")},
        capabilities=capabilities,
        provenance=provenance,
    )

    assert permitted.success is True, (
        "the opt-in path must still work, otherwise the isolation suite is not "
        "exercising what it claims to"
    )


@pytest.mark.security_regression
def test_probes_are_registered_only_through_the_explicit_opt_in_helper() -> None:
    registry = create_default_execution_registry()
    assert not registry.has_implementation("test_file_op")

    register_testing_handlers(registry)

    for implementation_id in PROBE_IMPLEMENTATIONS:
        assert registry.has_implementation(implementation_id), implementation_id


@pytest.mark.security_regression
def test_the_sandbox_defaults_to_refusing_probe_registration() -> None:
    """Default closed: the opt-in must be requested, never inferred."""
    from app.runtime.sandbox.process_sandbox import ProcessToolExecutionSandbox

    assert ProcessToolExecutionSandbox()._enable_testing_handlers is False
    assert (
        ProcessToolExecutionSandbox(enable_testing_handlers=True)._enable_testing_handlers
        is True
    )
