from fastapi.testclient import TestClient

from app.main import app
from app.models.jwt_claims import Role
from tests.conftest import auth_headers, register_test_agent

client = TestClient(app)
# Dedicated agent: this module asserts responses for an agent with no accumulated
# enforcement posture, which agent-1 no longer guarantees (M2b).
AGENT_ID = register_test_agent("runtime-api-agent", approved_tools=["file_read"])
agent_headers = auth_headers(agent_id=AGENT_ID, role=Role.AGENT)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_execute_request_received():
    response = client.post(
        f"/agents/{AGENT_ID}/execute",
        headers=agent_headers,
        json={
            "session_id": "session-1",
            "tool_id": "file_read",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-1",
        "agent_id": AGENT_ID,
        "tool_id": "file_read",
        "decision": "ALLOW",
        "findings": [],
        "risk_score": 0,
        "risk_level": "LOW",
        # M2b: agent-scoped posture the decision was derived from, additive.
        "enforcement_risk_score": 0,
        "enforcement_risk_level": "LOW",
        "response_type": "MONITOR",
        "response_reason": (
            "LOW risk requires monitor"
        ),
        # Null unless the request was refused before evaluation (M2b Step 4).
        "refusal_reason": None,
    }


def test_execute_response_includes_findings():
    session_id = "detection-session"

    for _ in range(2):
        response = client.post(
            f"/agents/{AGENT_ID}/execute",
            headers=agent_headers,
            json={
                "session_id": session_id,
                "tool_id": "file_write",
            },
        )

        assert response.json()["findings"] == []
        assert response.json()["risk_score"] == 0
        assert response.json()["risk_level"] == "LOW"
        assert (
            response.json()["response_type"]
            == "MONITOR"
        )
        assert (
            response.json()["response_reason"]
            == "LOW risk requires monitor"
        )

    response = client.post(
        f"/agents/{AGENT_ID}/execute",
        headers=agent_headers,
        json={
            "session_id": session_id,
            "tool_id": "file_write",
        },
    )

    assert response.status_code == 200
    assert len(response.json()["findings"]) == 1
    assert (
        response.json()["findings"][0]["rule_name"]
        == "EXCESSIVE_DENIALS"
    )
    assert response.json()["risk_score"] == 25
    assert response.json()["risk_level"] == "MEDIUM"
    assert (
        response.json()["response_type"]
        == "ALERT"
    )
    assert (
        response.json()["response_reason"]
        == "MEDIUM risk requires alert"
    )
