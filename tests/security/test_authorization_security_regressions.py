"""H-2 — Management plane authorization, and M-3 — scenario identity.

Review evidence (74e8c51)::

    [EXPOSED] AGENT role -> GET /api/v1/findings         = 200
    [EXPOSED] AGENT role -> GET /api/v1/risk-assessments = 200
    [EXPLOIT] ANALYST POST /api/scenarios/BEN-001/execute = 200

``require_roles()`` existed in ``app/api/auth.py`` and was never applied, so every
authenticated principal was equal on the management and scenario planes.

**H-2 is closed (M3 Step 1).** Every router is mounted behind the role set its plane
admits, so the management plane is operator-facing: an AGENT principal is a workload,
not an operator, and is refused.

**M-3 is reframed rather than fixed as originally stated.** The pending invariant here
said ANALYST must be refused scenario execution. M2a changed the premise underneath it:
a scenario now runs against a throwaway pipeline (ADR-013 isolation amendment) and can
no longer mutate live state, so scenario evaluation is an analyst capability the threat
model already grants. The invariant is rewritten, not deleted, in M3 Step 2 — together
with the sandbox identity, which still collides by name with the live default agent.

The negative control for the runtime route (ANALYST refused with 403) is already
covered by ``tests/api/test_jwt_boundary_auth.py`` and is not duplicated here.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.jwt_claims import Role
from app.services.scenario_runner_service import ScenarioRunnerService
from tests.conftest import auth_headers

client = TestClient(app)

# Every plane the application exposes, and the roles it admits. This table is the
# test's own statement of policy — the OpenAPI schema carries no authorization
# semantics, so nothing here is read back from the application. The partition must
# stay exhaustive: a route that matches no prefix below is a plane nobody authorized.
PLANE_ROLES: dict[str, set[Role]] = {
    "/agents/{agent_id}/execute": {Role.AGENT},
    "/api/scenarios": {Role.ANALYST, Role.ADMIN},
    "/api/v1": {Role.ANALYST, Role.ADMIN},
}

PUBLIC_PATHS = {"/health"}

# Security evidence a low-privilege agent principal should not be able to read
# for agents other than itself.
MANAGEMENT_EVIDENCE_ENDPOINTS = [
    "/api/v1/agents",
    "/api/v1/findings",
    "/api/v1/risk-assessments",
    "/api/v1/audit/events",
    "/api/v1/sessions",
]


@pytest.mark.security_regression
@pytest.mark.parametrize("endpoint", MANAGEMENT_EVIDENCE_ENDPOINTS)
def test_management_evidence_refuses_the_agent_role_rather_than_filtering_it(
    endpoint: str, agent_headers: dict[str, str], analyst_headers: dict[str, str]
) -> None:
    """These five endpoints returned 200 to an AGENT principal at the baseline.

    The promoted form asserts more than the refusal: the agent is *refused*, not served
    an empty collection. Returning 200 with nothing in it would satisfy "an agent sees
    no other agent's evidence" while quietly making the management plane agent-facing,
    and a later resource-scoping milestone could then widen it without review.

    The same endpoint answering an operator proves the refusal is about the principal
    rather than a route that stopped working.
    """
    refused = client.get(endpoint, headers=agent_headers)
    assert refused.status_code == 403

    operator = client.get(endpoint, headers=analyst_headers)
    assert operator.status_code == 200


@pytest.mark.security_regression
def test_every_route_belongs_to_an_authorized_plane() -> None:
    """The baseline recorded that the RBAC helper existed and no router applied it.

    This asserts *route publication* only: every path the application publishes falls
    within a plane this file declares a role set for. The schema is a route inventory
    and nothing more — it encodes no ANALYST, ADMIN or AGENT semantics, so a route
    passing here is not thereby shown to be authorized. What this catches is the case
    a per-endpoint test cannot: a router mounted under a prefix nobody has written a
    policy for. The policy itself is established by request-level tests below.
    """
    published = {
        path
        for path, methods in app.openapi()["paths"].items()
        if methods and path not in PUBLIC_PATHS
    }
    assert published, "no routes published; the schema assertion would be vacuous"

    unplaced = [
        path
        for path in published
        if not any(path.startswith(prefix) for prefix in PLANE_ROLES)
    ]
    assert unplaced == []


@pytest.mark.security_invariant
@pytest.mark.parametrize("endpoint", MANAGEMENT_EVIDENCE_ENDPOINTS)
def test_invariant_agent_role_is_refused_management_evidence(
    endpoint: str, agent_headers: dict[str, str]
) -> None:
    response = client.get(endpoint, headers=agent_headers)

    assert response.status_code == 403


@pytest.mark.security_invariant
def test_invariant_no_plane_admits_a_role_it_does_not_declare() -> None:
    """Each plane refuses every role outside its declared set, on every published route.

    The authorization semantics are established by the requests themselves — every one
    is issued against the running application with a real token, and the assertion is
    on the response. The OpenAPI schema supplies only the list of routes to try, in
    place of a hand-kept list that would go stale, so a route added to an existing
    plane is covered the moment it is published.

    Path parameters are filled with a value chosen not to exist: authorization is
    evaluated before any lookup, so a refusal must not depend on whether the target
    is real.
    """
    paths = app.openapi()["paths"]

    for path, operations in paths.items():
        if path in PUBLIC_PATHS:
            continue
        prefix = next(p for p in PLANE_ROLES if path.startswith(p))
        admitted = PLANE_ROLES[prefix]

        url = path.replace("{agent_id}", "no-such-agent")
        url = url.replace("{scenario_id}", "NO-SUCH-SCENARIO")
        url = url.replace("{session_id}", "no-such-session")
        url = url.replace("{finding_id}", "no-such-finding")

        for method in operations:
            for role in Role:
                if role in admitted:
                    continue
                response = client.request(
                    method.upper(), url, headers=auth_headers(role=role), json={}
                )
                assert response.status_code == 403, (
                    f"{method.upper()} {url} admitted {role.value}: "
                    f"{response.status_code}"
                )


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
