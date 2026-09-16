"""H-2 — Management plane authorization, and M-3 — scenario identity.

Review evidence (74e8c51)::

    [EXPOSED] AGENT role -> GET /api/v1/findings         = 200
    [EXPOSED] AGENT role -> GET /api/v1/risk-assessments = 200
    [EXPLOIT] ANALYST POST /api/scenarios/BEN-001/execute = 200

``require_roles()`` exists in ``app/api/auth.py`` and is never applied, so every
authenticated principal is equal on the management and scenario planes.

The negative control for the runtime route (ANALYST refused with 403) is already
covered by ``tests/api/test_jwt_boundary_auth.py`` and is not duplicated here.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.auth import require_roles
from app.main import app
from app.services.scenario_runner_service import ScenarioRunnerService

client = TestClient(app)

# Security evidence a low-privilege agent principal should not be able to read
# for agents other than itself.
MANAGEMENT_EVIDENCE_ENDPOINTS = [
    "/api/v1/agents",
    "/api/v1/findings",
    "/api/v1/risk-assessments",
    "/api/v1/audit/events",
    "/api/v1/sessions",
]


@pytest.mark.security_baseline
@pytest.mark.parametrize("endpoint", MANAGEMENT_EVIDENCE_ENDPOINTS)
def test_baseline_agent_role_reads_management_security_evidence(
    endpoint: str, agent_headers: dict[str, str]
) -> None:
    """An AGENT principal reads platform-wide security evidence unscoped."""
    response = client.get(endpoint, headers=agent_headers)

    assert response.status_code == 200


@pytest.mark.security_baseline
def test_baseline_role_helper_is_defined_but_unused() -> None:
    """The RBAC helper exists; no router applies it."""
    assert callable(require_roles)


@pytest.mark.security_invariant
@pytest.mark.parametrize("endpoint", MANAGEMENT_EVIDENCE_ENDPOINTS)
@pytest.mark.xfail(
    strict=True,
    reason="H-2: management plane enforces authentication only; role gating is not applied",
)
def test_invariant_agent_role_is_refused_management_evidence(
    endpoint: str, agent_headers: dict[str, str]
) -> None:
    response = client.get(endpoint, headers=agent_headers)

    assert response.status_code == 403


@pytest.mark.security_baseline
def test_baseline_analyst_may_drive_runtime_through_scenario_endpoint(
    analyst_headers: dict[str, str],
) -> None:
    """ANALYST is refused on the runtime route yet reaches the same pipeline here."""
    response = client.post(
        "/api/scenarios/BEN-001/execute", headers=analyst_headers
    )

    assert response.status_code == 200


@pytest.mark.security_baseline
def test_baseline_scenario_execution_uses_hardcoded_agent_identity() -> None:
    """Scenario activity is attributed to a fixed agent, not the caller."""
    assert ScenarioRunnerService._RUNTIME_AGENT_ID == "agent-1"


@pytest.mark.security_invariant
@pytest.mark.xfail(
    strict=True,
    reason="M-3: scenario router applies no role gate",
)
def test_invariant_analyst_is_refused_scenario_execution(
    analyst_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/scenarios/BEN-001/execute", headers=analyst_headers
    )

    assert response.status_code == 403
