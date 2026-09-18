"""Administrative reinstatement and governance visibility over HTTP (M2b Step 5).

Recovery from containment is a privileged mutation: ADMIN only, attributed to the
authenticated principal, and refused for an agent that is not contained. Authorization
is evaluated before the agent is looked up, so the route cannot be used to discover
which agent identifiers exist.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.main import app
from app.models.agent import AgentStatus
from app.models.jwt_claims import Role
from tests.conftest import auth_headers, register_test_agent

client = TestClient(app)

ADMIN_HEADERS = auth_headers(agent_id="admin-agent", role=Role.ADMIN, subject="admin-1")


@pytest.fixture
def contained_agent() -> str:
    """A registered agent that the runtime has contained.

    Each test gets its own agent: enforcement history accumulates per agent by design,
    so sharing one would make a test depend on how many tests ran before it.
    """
    agent_id = register_test_agent(f"reinstate-{uuid4().hex[:8]}")
    dependencies.execution_authority.suspend_issuance(agent_id)
    dependencies.agent_service.suspend_agent(agent_id, reason="critical risk posture")
    return agent_id


def reinstate(agent_id: str, headers: dict[str, str], reason: str = "investigated"):
    return client.post(
        f"/api/v1/agents/{agent_id}/reinstate",
        headers=headers,
        json={"reason": reason},
    )


class TestReinstatement:
    def test_admin_returns_a_contained_agent_to_service(self, contained_agent: str) -> None:
        response = reinstate(contained_agent, ADMIN_HEADERS)

        assert response.status_code == 200
        assert response.json()["status"] == "ACTIVE"
        assert dependencies.execution_authority.issuance_suspended(contained_agent) is False

    def test_the_actor_comes_from_the_token_not_the_body(self, contained_agent: str) -> None:
        client.post(
            f"/api/v1/agents/{contained_agent}/reinstate",
            headers=ADMIN_HEADERS,
            json={"reason": "investigated", "actor": "someone-else"},
        )

        transition = dependencies.agent_service.list_transitions(contained_agent)[-1]
        assert transition.actor == "admin-1"

    def test_an_agent_that_is_not_contained_is_refused(self) -> None:
        agent_id = register_test_agent(f"reinstate-active-{uuid4().hex[:8]}")

        response = reinstate(agent_id, ADMIN_HEADERS)

        assert response.status_code == 409
        assert "not suspended" in response.json()["detail"]

    def test_an_unknown_agent_is_not_found(self) -> None:
        response = reinstate("no-such-agent", ADMIN_HEADERS)

        assert response.status_code == 404

    @pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}])
    def test_a_reason_is_required(self, contained_agent: str, body: dict) -> None:
        response = client.post(
            f"/api/v1/agents/{contained_agent}/reinstate",
            headers=ADMIN_HEADERS,
            json=body,
        )

        assert response.status_code == 422
        assert (
            dependencies.agent_service.get_agent(contained_agent).status
            == AgentStatus.SUSPENDED
        )


class TestReinstatementAuthorization:
    @pytest.mark.parametrize("role", [Role.ANALYST, Role.AGENT])
    def test_only_admins_may_reinstate(self, contained_agent: str, role: Role) -> None:
        response = reinstate(contained_agent, auth_headers(role=role))

        assert response.status_code == 403
        assert (
            dependencies.agent_service.get_agent(contained_agent).status
            == AgentStatus.SUSPENDED
        )

    def test_an_unauthenticated_caller_is_refused(self, contained_agent: str) -> None:
        response = client.post(
            f"/api/v1/agents/{contained_agent}/reinstate",
            json={"reason": "investigated"},
        )

        assert response.status_code == 401

    def test_the_route_is_not_an_identifier_oracle(self) -> None:
        """An unauthorized caller learns nothing about which agents exist."""
        known = reinstate("agent-1", auth_headers(role=Role.ANALYST))
        unknown = reinstate("definitely-not-an-agent", auth_headers(role=Role.ANALYST))

        assert known.status_code == 403
        assert unknown.status_code == 403
        assert known.json()["detail"] == unknown.json()["detail"]


class TestEnforcementVisibility:
    def test_state_and_history_are_reported(self, contained_agent: str) -> None:
        response = client.get(
            f"/api/v1/agents/{contained_agent}/enforcement", headers=ADMIN_HEADERS
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "SUSPENDED"
        assert body["suspension_reason"] == "critical risk posture"
        assert [transition["action"] for transition in body["transitions"]] == ["SUSPEND"]
        assert body["transitions"][0]["actor"] == "runtime"

    def test_history_records_recovery_too(self, contained_agent: str) -> None:
        reinstate(contained_agent, ADMIN_HEADERS, reason="cleared after review")

        body = client.get(
            f"/api/v1/agents/{contained_agent}/enforcement", headers=ADMIN_HEADERS
        ).json()

        assert [transition["action"] for transition in body["transitions"]] == [
            "SUSPEND",
            "REINSTATE",
        ]
        assert body["transitions"][-1]["actor"] == "admin-1"
        assert body["transitions"][-1]["reason"] == "cleared after review"
        assert body["enforcement_baseline_at"] is not None

    def test_an_unknown_agent_is_not_found(self) -> None:
        response = client.get(
            "/api/v1/agents/no-such-agent/enforcement", headers=ADMIN_HEADERS
        )

        assert response.status_code == 404

    def test_an_analyst_may_read_governance_history(self) -> None:
        """Reading enforcement history is an operator capability, not an administrative one.

        Since M3 the management plane admits ANALYST and ADMIN and refuses AGENT. This
        route is deliberately not narrowed to ADMIN: investigating why an agent was
        contained is analyst work, while *undoing* it is not.
        """
        response = client.get(
            "/api/v1/agents/agent-1/enforcement", headers=auth_headers(role=Role.ANALYST)
        )

        assert response.status_code == 200

    def test_an_agent_may_not_read_governance_history(self) -> None:
        """Including its own: an agent is a workload, not an operator (M3 Decision 1)."""
        response = client.get(
            "/api/v1/agents/agent-1/enforcement",
            headers=auth_headers(agent_id="agent-1", role=Role.AGENT),
        )

        assert response.status_code == 403
