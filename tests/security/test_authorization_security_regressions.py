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

from app.api import dependencies
from app.main import app
from app.models.jwt_claims import Role
from app.services.scenario_runner_service import ScenarioRunnerService
from app.services.scenario_sandbox import build_scenario_sandbox
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


@pytest.mark.security_regression
def test_the_analyst_scenario_path_no_longer_reaches_the_live_pipeline(
    analyst_headers: dict[str, str],
) -> None:
    """The baseline finding was the *reach*, not the status code.

    At `74e8c51` this request was recorded as ``[EXPLOIT]`` because an ANALYST refused
    on the runtime route reached the same live pipeline through here. The status code
    is unchanged — an analyst still gets 200, and that is now intended — so this test
    asserts what actually changed: the request no longer touches live state.

    Written as an end-to-end delta over the shared singletons rather than an object
    identity check, which ``tests/services/test_scenario_sandbox.py`` already covers.
    A wiring mistake that handed the runner the live services would pass every identity
    assertion in that file and fail here.
    """
    live_agent = "agent-1"
    findings_before = dependencies.findings_service.list_findings(agent_id=live_agent)
    posture_before = dependencies.risk_service.get_agent_posture(live_agent)
    sessions_before = {s.session_id for s in dependencies.session_service.list_sessions()}
    audit_before = len(dependencies.audit_service.list_events())
    agents_before = {agent.agent_id for agent in dependencies.agent_service.list_agents()}

    response = client.post("/api/scenarios/TOOL-002/execute", headers=analyst_headers)

    assert response.status_code == 200
    assert dependencies.findings_service.list_findings(agent_id=live_agent) == findings_before
    assert dependencies.risk_service.get_agent_posture(live_agent) == posture_before
    assert {
        s.session_id for s in dependencies.session_service.list_sessions()
    } == sessions_before
    assert len(dependencies.audit_service.list_events()) == audit_before
    assert {
        agent.agent_id for agent in dependencies.agent_service.list_agents()
    } == agents_before


@pytest.mark.security_regression
def test_scenario_identity_is_sandbox_local(
    analyst_headers: dict[str, str],
) -> None:
    """The baseline recorded scenario activity attributed to the live default agent.

    Isolation kept that from corrupting state, but it left the identifier itself
    misleading: a result reporting activity by ``agent-1`` names an agent an operator
    can look up in the registry. The identity is now sandbox-local by construction.
    """
    assert ScenarioRunnerService._RUNTIME_AGENT_ID != "agent-1"
    assert ScenarioRunnerService._RUNTIME_AGENT_ID == "scenario-sandbox-agent"

    registered = {agent.agent_id for agent in dependencies.agent_service.list_agents()}
    assert ScenarioRunnerService._RUNTIME_AGENT_ID not in registered


@pytest.mark.security_invariant
def test_invariant_analyst_may_execute_scenarios_in_isolation(
    analyst_headers: dict[str, str],
) -> None:
    """Rewritten, not deleted (M3 Step 2).

    This invariant previously asserted ``ANALYST -> scenario execution = DENY``. M2a
    changed the premise underneath it: a scenario now runs against a throwaway pipeline
    (ADR-013 isolation amendment) and can no longer mutate live runtime state, so the
    escalation the original invariant guarded against no longer exists. Scenario
    evaluation is an analyst capability the threat model already grants.

    The security property is therefore restated rather than dropped, and the permission
    and the isolation are asserted together, because the permission is only safe while
    the isolation holds::

        ANALYST may execute security validation scenarios,
        but scenario execution must remain isolated from live enforcement state.

    Widening the role gate without the sandbox, or losing the sandbox while the gate
    stays open, must both fail here.
    """
    live_agent = "agent-1"
    status_before = dependencies.agent_service.get_agent(live_agent).status
    posture_before = dependencies.risk_service.get_agent_posture(live_agent)
    findings_before = dependencies.findings_service.list_findings(agent_id=live_agent)
    suspended_before = dependencies.execution_authority.issuance_suspended(live_agent)
    transitions_before = dependencies.agent_service.list_transitions(live_agent)

    # TOOL-002 drives three denials through the pipeline, which is enough to raise an
    # EXCESSIVE_DENIALS finding — durable evidence that would accumulate into an
    # agent's enforcement posture, and eventually contain it, were the run not
    # isolated. It runs from a tool sequence, so no model provider is involved and the
    # outcome is deterministic.
    response = client.post("/api/scenarios/TOOL-002/execute", headers=analyst_headers)

    assert response.status_code == 200

    assert dependencies.agent_service.get_agent(live_agent).status == status_before
    assert dependencies.risk_service.get_agent_posture(live_agent) == posture_before
    assert dependencies.findings_service.list_findings(agent_id=live_agent) == findings_before
    assert dependencies.execution_authority.issuance_suspended(live_agent) is suspended_before
    assert dependencies.agent_service.list_transitions(live_agent) == transitions_before


@pytest.mark.security_invariant
def test_invariant_scenario_activity_is_never_attributed_to_a_live_agent(
    analyst_headers: dict[str, str],
) -> None:
    """Every record a scenario run produces names an identity no live agent holds.

    The scenario execution response carries no agent field at all, so the collision
    this rename removes was never visible in the API response: it lived in the records
    the run produces — session events, findings and audit events inside the sandbox —
    and in anything downstream that reads them. Asserting only on the response would
    therefore prove nothing, so the run's own records are inspected directly.

    The live registry is consulted rather than a hardcoded string, so restoring any
    identifier a real agent uses fails here, not only the specific former value.
    """
    sandbox_id = ScenarioRunnerService._RUNTIME_AGENT_ID
    registered = {agent.agent_id for agent in dependencies.agent_service.list_agents()}
    assert sandbox_id not in registered

    sandbox = build_scenario_sandbox()
    scenario = dependencies.scenario_registry.get_scenario("TOOL-002")
    ScenarioRunnerService(runtime_service=sandbox.runtime).run(scenario)

    attributed = (
        [event.agent_id for session in sandbox.session_service.list_sessions()
         for event in sandbox.session_service.list_events(session.session_id)]
        + [finding.agent_id for finding in sandbox.findings_service.list_findings()]
        + [event.agent_id for event in sandbox.audit_service.list_events()]
    )

    assert attributed, "the run produced no attributed records; the assertion is vacuous"
    assert set(attributed).isdisjoint(registered)


@pytest.mark.security_regression
def test_the_scenario_response_exposes_no_agent_identity(
    analyst_headers: dict[str, str],
) -> None:
    """The response contract carries no agent field, and must not acquire a live one.

    Recorded so that adding agent attribution to the response later — a reasonable
    reporting change — cannot reintroduce a live identifier by accident.
    """
    response = client.post("/api/scenarios/BEN-001/execute", headers=analyst_headers)
    assert response.status_code == 200

    registered = {agent.agent_id for agent in dependencies.agent_service.list_agents()}
    live_sessions = {s.session_id for s in dependencies.session_service.list_sessions()}
    body = response.json()

    assert body["session_id"] not in live_sessions
    for value in body.values():
        if isinstance(value, str):
            assert value not in registered
