import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import risk_service
from app.main import app
from app.models.finding import Finding, Severity

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_risk_state():
    risk_service.clear()
    yield
    risk_service.clear()


def create_finding(
    severity: Severity,
    finding_id: str = "finding-1",
    session_id: str = "session-1",
    agent_id: str = "agent-1",
) -> Finding:
    return Finding(
        finding_id=finding_id,
        session_id=session_id,
        agent_id=agent_id,
        rule_name="TEST_RULE",
        severity=severity,
        description="Test finding for API",
    )


def test_list_risk_assessments_empty():
    response = client.get("/api/v1/risk-assessments")
    assert response.status_code == 200
    assert response.json() == []


def test_list_risk_assessments_populated_and_filtered():
    risk_service.assess_session("session-1", "agent-1", [create_finding(Severity.HIGH, "f1")])
    risk_service.assess_session("session-2", "agent-2", [create_finding(Severity.CRITICAL, "f2", session_id="session-2", agent_id="agent-2")])

    # List all
    res_all = client.get("/api/v1/risk-assessments")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert len(data_all) == 2

    # Filter by risk_level=CRITICAL
    res_crit = client.get("/api/v1/risk-assessments?risk_level=CRITICAL")
    assert res_crit.status_code == 200
    data_crit = res_crit.json()
    assert len(data_crit) == 1
    assert data_crit[0]["session_id"] == "session-2"
    assert data_crit[0]["risk_level"] == "CRITICAL"

    # Filter by agent_id=agent-1
    res_agent1 = client.get("/api/v1/risk-assessments?agent_id=agent-1")
    assert res_agent1.status_code == 200
    data_agent1 = res_agent1.json()
    assert len(data_agent1) == 1
    assert data_agent1[0]["session_id"] == "session-1"
    assert data_agent1[0]["risk_score"] == 50
    assert data_agent1[0]["risk_level"] == "HIGH"


def test_get_risk_assessment_by_session():
    risk_service.assess_session("session-100", "agent-1", [create_finding(Severity.MEDIUM, "f100", session_id="session-100")])

    res = client.get("/api/v1/risk-assessments/session-100")
    assert res.status_code == 200
    dto = res.json()
    assert dto["session_id"] == "session-100"
    assert dto["agent_id"] == "agent-1"
    assert dto["risk_score"] == 25
    assert dto["risk_level"] == "MEDIUM"
    assert dto["finding_count"] == 1
    assert "assessed_at" in dto


def test_get_risk_assessment_with_agent_id_filter():
    fA = create_finding(Severity.HIGH, "fA", session_id="shared-sess", agent_id="agent-A")
    fB = create_finding(Severity.LOW, "fB", session_id="shared-sess", agent_id="agent-B")

    risk_service.assess_session("shared-sess", "agent-A", [fA])
    risk_service.assess_session("shared-sess", "agent-B", [fB])

    resA = client.get("/api/v1/risk-assessments/shared-sess?agent_id=agent-A")
    assert resA.status_code == 200
    dtoA = resA.json()
    assert dtoA["agent_id"] == "agent-A"
    assert dtoA["risk_level"] == "HIGH"
    assert dtoA["risk_score"] == 50

    resB = client.get("/api/v1/risk-assessments/shared-sess?agent_id=agent-B")
    assert resB.status_code == 200
    dtoB = resB.json()
    assert dtoB["agent_id"] == "agent-B"
    assert dtoB["risk_level"] == "LOW"
    assert dtoB["risk_score"] == 10


def test_get_risk_assessment_ambiguous_scope_returns_400():
    fA = create_finding(Severity.HIGH, "fA", session_id="shared-sess", agent_id="agent-A")
    fB = create_finding(Severity.LOW, "fB", session_id="shared-sess", agent_id="agent-B")

    risk_service.assess_session("shared-sess", "agent-A", [fA])
    risk_service.assess_session("shared-sess", "agent-B", [fB])

    # Unscoped request on shared session MUST return 400 Bad Request and NOT leak either assessment
    res = client.get("/api/v1/risk-assessments/shared-sess")
    assert res.status_code == 400
    assert "agent_id is required" in res.json()["detail"]


def test_get_risk_assessment_not_found():
    res = client.get("/api/v1/risk-assessments/nonexistent-session")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]


def test_risk_assessments_read_only_methods():
    for method in [client.post, client.put, client.patch, client.delete]:
        res = method("/api/v1/risk-assessments")
        assert res.status_code == 405
