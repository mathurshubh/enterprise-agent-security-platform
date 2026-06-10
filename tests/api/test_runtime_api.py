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
        "decision": "DENY",
        "findings": [],
    }


def test_execute_response_includes_findings():
    session_id = "detection-session"

    for _ in range(2):
        response = client.post(
            "/agents/agent-1/execute",
            json={
                "session_id": session_id,
                "tool_id": "file_read",
            },
        )

        assert response.json()["findings"] == []

    response = client.post(
        "/agents/agent-1/execute",
        json={
            "session_id": session_id,
            "tool_id": "file_read",
        },
    )

    assert response.status_code == 200
    assert len(response.json()["findings"]) == 1
    assert (
        response.json()["findings"][0]["rule_name"]
        == "EXCESSIVE_DENIALS"
    )
