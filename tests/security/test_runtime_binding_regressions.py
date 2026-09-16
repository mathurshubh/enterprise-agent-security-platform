"""H-5 — Authorization/execution divergence, and M-2 — API resource omission.

Review evidence (74e8c51)::

    pipeline decision for resource='notes.txt': ALLOW
    [UNBOUND] executed file_read with path='secrets.txt' after authorizing 'notes.txt'
    [ok] pipeline decision for resource='secrets.txt' (when actually supplied): DENY

``RuntimeService`` issues a decision about a ``resource`` string while execution
later receives a separate ``parameters`` mapping. Nothing requires the two to
describe the same object, so containment depends on caller discipline.

The invariant tests below express the contract M1 must establish. They are
written against the future API deliberately: they must start passing once the
binding exists, and ``strict=True`` turns that transition into a CI signal.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.runtime import ExecuteRequest
from app.main import app
from app.models.audit_event import Decision
from app.runtime.tool_executor import DefaultToolExecutor, ToolExecutionError

from .conftest import BENIGN_FILE, PROTECTED_FILE, PROTECTED_MARKER

client = TestClient(app)

# The canonical representation the future binding must compare against. Stated
# explicitly so the contract does not depend on dictionary ordering or on
# incidental JSON serialisation.
CANONICAL_AUTHORIZED_PARAMETERS = {"path": BENIGN_FILE}


@pytest.mark.security_baseline
def test_baseline_execution_ignores_the_authorized_resource(
    build_runtime, security_workspace: Path
) -> None:
    """Authorizing one resource does not constrain execution of another."""
    env = build_runtime(workspace=security_workspace)

    result = env.runtime.execute(
        session_id="corpus-binding-allow",
        agent_id=env.agent_id,
        tool_id="file_read",
        resource=BENIGN_FILE,
        parameters=dict(CANONICAL_AUTHORIZED_PARAMETERS),
    )
    assert result.event.decision == Decision.ALLOW

    descriptor = env.tool_registry.resolve("file_read")
    executed = DefaultToolExecutor().execute_descriptor(
        descriptor, {"path": PROTECTED_FILE}
    )

    assert executed == PROTECTED_MARKER


@pytest.mark.security_regression
def test_protected_resource_is_denied_when_actually_supplied(
    build_runtime, security_workspace: Path
) -> None:
    """Positive control: the policy works when it is given the real resource."""
    env = build_runtime(workspace=security_workspace)

    result = env.runtime.execute(
        session_id="corpus-binding-deny",
        agent_id=env.agent_id,
        tool_id="file_read",
        resource=PROTECTED_FILE,
    )

    assert result.event.decision == Decision.DENY


@pytest.mark.security_invariant
@pytest.mark.xfail(
    strict=True,
    reason="H-5: RuntimeResult carries no authorized-parameter binding yet (M1)",
)
def test_invariant_decision_carries_authorized_parameter_binding(
    build_runtime, security_workspace: Path
) -> None:
    env = build_runtime(workspace=security_workspace)

    result = env.runtime.execute(
        session_id="corpus-binding-contract",
        agent_id=env.agent_id,
        tool_id="file_read",
        resource=BENIGN_FILE,
        parameters=dict(CANONICAL_AUTHORIZED_PARAMETERS),
    )

    authorized = getattr(result, "authorized_parameters", None)
    assert authorized == CANONICAL_AUTHORIZED_PARAMETERS


@pytest.mark.security_invariant
@pytest.mark.xfail(
    strict=True,
    reason="H-5: the executor accepts any parameters; mismatched execution must be refused (M1)",
)
def test_invariant_executor_refuses_parameters_that_were_not_authorized(
    build_runtime, security_workspace: Path
) -> None:
    env = build_runtime(workspace=security_workspace)

    env.runtime.execute(
        session_id="corpus-binding-refusal",
        agent_id=env.agent_id,
        tool_id="file_read",
        resource=BENIGN_FILE,
        parameters=dict(CANONICAL_AUTHORIZED_PARAMETERS),
    )

    descriptor = env.tool_registry.resolve("file_read")

    with pytest.raises((ToolExecutionError, PermissionError, ValueError)):
        DefaultToolExecutor().execute_descriptor(
            descriptor, {"path": PROTECTED_FILE}
        )


@pytest.mark.security_baseline
def test_baseline_execute_request_cannot_express_a_resource() -> None:
    """The HTTP contract has no field for the object being acted on."""
    fields = set(ExecuteRequest.model_fields)

    assert fields == {
        "session_id",
        "tool_id",
        "user_prompt",
        "model_output",
        "tool_output",
    }
    assert "resource" not in fields
    assert "parameters" not in fields


@pytest.mark.security_baseline
def test_baseline_protected_resource_is_allowed_over_http(
    agent_headers: dict[str, str],
) -> None:
    """Resource-aware policy is unreachable through the main API."""
    response = client.post(
        "/agents/agent-1/execute",
        headers=agent_headers,
        json={
            "session_id": "corpus-m2-resource-omission",
            "tool_id": "file_read",
            "user_prompt": "read secrets.txt",
        },
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "ALLOW"


@pytest.mark.security_invariant
@pytest.mark.xfail(
    strict=True,
    reason="M-2: ExecuteRequest cannot carry a resource, so PROTECTED_RESOURCES never fires over HTTP (M1)",
)
def test_invariant_http_api_denies_protected_resource(
    agent_headers: dict[str, str],
) -> None:
    response = client.post(
        "/agents/agent-1/execute",
        headers=agent_headers,
        json={
            "session_id": "corpus-m2-resource-contract",
            "tool_id": "file_read",
            "resource": PROTECTED_FILE,
        },
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "DENY"
