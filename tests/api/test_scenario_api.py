from fastapi.testclient import TestClient

from app.main import app
from app.models.jwt_claims import Role
from tests.conftest import auth_headers

client = TestClient(app, headers=auth_headers(role=Role.ADMIN))


class TestListScenarios:
    def test_returns_200_and_scenario_list(self) -> None:
        response = client.get("/api/scenarios")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 19

    def test_filter_by_category(self) -> None:
        response = client.get("/api/scenarios?category=PROMPT_INJECTION")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        for item in data:
            assert item["category"] == "PROMPT_INJECTION"

    def test_filter_by_severity(self) -> None:
        response = client.get("/api/scenarios?severity=HIGH")
        assert response.status_code == 200
        data = response.json()
        for item in data:
            assert item["severity"] == "HIGH"

    def test_filter_by_tag(self) -> None:
        response = client.get("/api/scenarios?tag=OWASP-LLM01")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        for item in data:
            assert "OWASP-LLM01" in item["tags"]


class TestGetScenario:
    def test_returns_200_for_existing_scenario(self) -> None:
        response = client.get("/api/scenarios/PI-001")
        assert response.status_code == 200
        data = response.json()
        assert data["scenario_id"] == "PI-001"
        assert data["category"] == "PROMPT_INJECTION"
        assert "expected_risk" in data
        assert "expected_findings" in data
        assert "tool_sequence" in data

    def test_returns_404_for_nonexistent_scenario(self) -> None:
        response = client.get("/api/scenarios/NONEXISTENT-999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestExecuteScenario:
    def test_execute_existing_scenario(self) -> None:
        response = client.post("/api/scenarios/BEN-001/execute")
        assert response.status_code == 200
        data = response.json()
        assert data["scenario_id"] == "BEN-001"
        assert data["status"] == "COMPLETED"
        assert data["passed"] is True
        assert data["observed_decision"] == "ALLOW"
        assert data["observed_risk_level"] == "LOW"

    def test_execute_nonexistent_scenario(self) -> None:
        response = client.post("/api/scenarios/NONEXISTENT-999/execute")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
