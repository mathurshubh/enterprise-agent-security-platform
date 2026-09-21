"""Risk assessment endpoints, derived from authoritative findings (M4-RISK).

Both endpoints reconstruct on read; nothing is stored (ADR-027 Decision A). These
tests therefore set up **findings** and assert on the assessment derived from them,
rather than writing assessments into a store and reading them back.

That change is deliberate. The previous suite populated `RiskService` directly and
isolated itself with `risk_service.clear()`, which coupled it to the materialized
store this milestone removed. Rebuilding the same isolation around the findings store
would preserve the old architecture through test scaffolding, so instead each test
owns a unique session identifier and queries within it — the shared evidence store is
append-only and other modules' findings are simply not in scope.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import findings_service
from app.main import app
from app.models.finding import Finding, Severity
from app.models.jwt_claims import Role
from tests.conftest import auth_headers

client = TestClient(app, headers=auth_headers(role=Role.ADMIN))


@pytest.fixture
def session_id() -> str:
    """A session identifier no other test uses."""
    return f"risk-api-{uuid4().hex[:12]}"


def record(
    severity: Severity,
    session_id: str,
    agent_id: str = "agent-1",
    finding_id: str | None = None,
) -> Finding:
    """Put one authoritative finding in the evidence store."""
    finding = Finding(
        finding_id=finding_id or f"finding-{uuid4().hex[:12]}",
        session_id=session_id,
        agent_id=agent_id,
        rule_name="TEST_RULE",
        severity=severity,
        description="Test finding for API",
    )
    return findings_service.record_new_findings([finding])[0]


class TestCollection:
    def test_a_session_without_evidence_has_no_assessment(self, session_id: str) -> None:
        """Evidence-defined existence (M4-RISK).

        Until this milestone the runtime wrote a LOW/0 assessment on every request,
        so a session that executed cleanly appeared in this collection. Existence now
        follows the evidence, and a session with none is simply absent.
        """
        response = client.get(f"/api/v1/risk-assessments?session_id={session_id}")

        assert response.status_code == 200
        assert response.json() == []

    def test_assessments_are_derived_from_findings(self, session_id: str) -> None:
        record(Severity.HIGH, session_id)

        response = client.get(f"/api/v1/risk-assessments?session_id={session_id}")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["session_id"] == session_id
        assert body[0]["agent_id"] == "agent-1"
        assert body[0]["risk_score"] == 50
        assert body[0]["risk_level"] == "HIGH"
        assert body[0]["finding_count"] == 1

    def test_filter_by_agent(self, session_id: str) -> None:
        record(Severity.HIGH, session_id, agent_id="agent-A")
        record(Severity.LOW, session_id, agent_id="agent-B")

        response = client.get(
            f"/api/v1/risk-assessments?session_id={session_id}&agent_id=agent-A"
        )

        body = response.json()
        assert len(body) == 1
        assert body[0]["agent_id"] == "agent-A"
        assert body[0]["risk_level"] == "HIGH"

    def test_filter_by_risk_level(self, session_id: str) -> None:
        """A risk level is a property of the assessment, so the filter is applied
        after derivation rather than pushed down to the evidence."""
        record(Severity.CRITICAL, session_id, agent_id="agent-A")
        record(Severity.LOW, session_id, agent_id="agent-B")

        critical = client.get(
            f"/api/v1/risk-assessments?session_id={session_id}&risk_level=CRITICAL"
        ).json()

        assert len(critical) == 1
        assert critical[0]["agent_id"] == "agent-A"
        assert critical[0]["risk_level"] == "CRITICAL"

    def test_one_assessment_per_session_and_agent_pair(self, session_id: str) -> None:
        """Several findings for one pair aggregate into a single assessment."""
        record(Severity.LOW, session_id)
        record(Severity.MEDIUM, session_id)

        body = client.get(f"/api/v1/risk-assessments?session_id={session_id}").json()

        assert len(body) == 1
        assert body[0]["finding_count"] == 2
        assert body[0]["risk_score"] == 35

    def test_ordering_is_deterministic_by_session_id(self) -> None:
        """Explicit rather than inherited: the previous ordering was whatever order
        the materialized store happened to hold."""
        prefix = f"risk-order-{uuid4().hex[:8]}"
        for suffix in ("c", "a", "b"):
            record(Severity.LOW, f"{prefix}-{suffix}")

        body = client.get("/api/v1/risk-assessments").json()
        ours = [a["session_id"] for a in body if a["session_id"].startswith(prefix)]

        assert ours == sorted(ours)
        assert ours == [f"{prefix}-a", f"{prefix}-b", f"{prefix}-c"]


class TestSingleSession:
    def test_returns_the_assessment_for_a_session(self, session_id: str) -> None:
        record(Severity.MEDIUM, session_id)

        response = client.get(f"/api/v1/risk-assessments/{session_id}")

        assert response.status_code == 200
        dto = response.json()
        assert dto["session_id"] == session_id
        assert dto["agent_id"] == "agent-1"
        assert dto["risk_score"] == 25
        assert dto["risk_level"] == "MEDIUM"
        assert dto["finding_count"] == 1
        assert "assessed_at" in dto

    def test_agent_scope_selects_one_agents_evidence(self, session_id: str) -> None:
        record(Severity.HIGH, session_id, agent_id="agent-A")
        record(Severity.LOW, session_id, agent_id="agent-B")

        a = client.get(f"/api/v1/risk-assessments/{session_id}?agent_id=agent-A").json()
        b = client.get(f"/api/v1/risk-assessments/{session_id}?agent_id=agent-B").json()

        assert (a["agent_id"], a["risk_level"], a["risk_score"]) == ("agent-A", "HIGH", 50)
        assert (b["agent_id"], b["risk_level"], b["risk_score"]) == ("agent-B", "LOW", 10)

    def test_an_ambiguous_scope_is_refused_and_leaks_neither(self, session_id: str) -> None:
        """Unchanged in meaning, re-derived from its source: the ambiguity is now
        about which agents hold evidence in the session."""
        record(Severity.HIGH, session_id, agent_id="agent-A")
        record(Severity.LOW, session_id, agent_id="agent-B")

        response = client.get(f"/api/v1/risk-assessments/{session_id}")

        assert response.status_code == 400
        assert "agent_id is required" in response.json()["detail"]
        assert "agent-A" not in response.text
        assert "agent-B" not in response.text

    def test_an_unknown_session_is_not_found(self) -> None:
        response = client.get("/api/v1/risk-assessments/nonexistent-session")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_a_session_without_evidence_is_not_found(self, session_id: str) -> None:
        """The documented contract change: a session that executed without producing
        findings returns 404 where it previously returned LOW/0."""
        response = client.get(f"/api/v1/risk-assessments/{session_id}")

        assert response.status_code == 404

    def test_an_agent_without_evidence_in_the_session_is_not_found(
        self, session_id: str
    ) -> None:
        record(Severity.HIGH, session_id, agent_id="agent-A")

        response = client.get(f"/api/v1/risk-assessments/{session_id}?agent_id=agent-B")

        assert response.status_code == 404


class TestDerivationIsReproducible:
    def test_two_reads_of_unchanged_evidence_are_identical(self, session_id: str) -> None:
        """Including `assessed_at`, which comes from the evidence rather than a
        read-time clock. A derived view that changes on every read cannot be
        compared, cached or reasoned about."""
        record(Severity.HIGH, session_id)

        first = client.get(f"/api/v1/risk-assessments/{session_id}").json()
        second = client.get(f"/api/v1/risk-assessments/{session_id}").json()

        assert first == second


def test_risk_assessments_read_only_methods() -> None:
    for method in (client.post, client.put, client.patch, client.delete):
        assert method("/api/v1/risk-assessments").status_code == 405
