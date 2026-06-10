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
        "status": "received",
        "agent_id": "agent-1",
    }
