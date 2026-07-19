from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_execute_request_received():
    response = client.post(
        "/agents/agent-1/execute",
        json={
            "session_id": "session-1",
            "tool_id": "file_read",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-1",
        "agent_id": "agent-1",
        "tool_id": "file_read",
        "decision": "ALLOW",
        "findings": [],
        "risk_score": 0,
        "risk_level": "LOW",
        "response_type": "MONITOR",
        "response_reason": (
            "LOW risk requires monitor"
        ),
    }


def test_execute_response_includes_findings():
    session_id = "detection-session"

    for _ in range(2):
        response = client.post(
            "/agents/agent-1/execute",
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
        "/agents/agent-1/execute",
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
