"""Agent-scoped enforcement posture (M2b Step 2).

Two scopes are derived from the same authoritative findings:

    assess_session()  → session-scoped RiskAssessment   (reporting, unchanged)
    assess_agent()    → agent-scoped AgentRiskPosture   (enforcement)

These tests cover the agent scope: accumulation across sessions, the reinstatement
baseline, and the refusal to assess a finding that belongs to another agent.
"""

from datetime import datetime, timezone

import pytest

from app.models.finding import Finding, Severity
from app.models.risk_assessment import RiskLevel
from app.services.risk_service import FindingScopeError, RiskService


def make_finding(
    finding_id: str,
    agent_id: str = "agent-1",
    session_id: str = "session-1",
    severity: Severity = Severity.HIGH,
    created_at: datetime | None = None,
) -> Finding:
    finding = Finding(
        finding_id=finding_id,
        session_id=session_id,
        agent_id=agent_id,
        rule_name="PROMPT_INJECTION",
        severity=severity,
        description="test finding",
    )
    if created_at is not None:
        return finding.model_copy(update={"created_at": created_at})
    return finding


class TestAccumulation:
    def test_posture_accumulates_across_sessions(self) -> None:
        service = RiskService()

        posture = service.assess_agent(
            "agent-1",
            [
                make_finding("f-1", session_id="session-1"),
                make_finding("f-2", session_id="session-2"),
            ],
        )

        assert posture.risk_score == 100
        assert posture.risk_level == RiskLevel.CRITICAL
        assert posture.finding_count == 2

    def test_posture_without_findings_is_low(self) -> None:
        posture = RiskService().assess_agent("agent-1", [])

        assert posture.risk_score == 0
        assert posture.risk_level == RiskLevel.LOW
        assert posture.finding_count == 0

    def test_posture_is_stored_and_retrievable(self) -> None:
        service = RiskService()
        assert service.get_agent_posture("agent-1") is None

        posture = service.assess_agent("agent-1", [make_finding("f-1")])

        assert service.get_agent_posture("agent-1") == posture

    def test_scoring_matches_the_session_scope(self) -> None:
        """Both scopes apply the same deterministic weights and thresholds."""
        service = RiskService()
        findings = [make_finding("f-1", severity=Severity.MEDIUM)]

        session = service.assess_session("session-1", "agent-1", findings)
        agent = service.assess_agent("agent-1", findings)

        assert (agent.risk_score, agent.risk_level) == (
            session.risk_score,
            session.risk_level,
        )

    def test_agent_assessment_does_not_disturb_session_assessments(self) -> None:
        service = RiskService()
        findings = [make_finding("f-1")]
        session = service.assess_session("session-1", "agent-1", findings)

        service.assess_agent("agent-1", findings)

        assert service.get_assessment("session-1", "agent-1") == session


class TestBaseline:
    """The baseline is recorded for attribution; eligibility is applied by the store.

    Detection rules set ``Finding.created_at`` to a deterministic value, so it cannot
    separate historical evidence from evidence recorded after a reinstatement. That
    separation lives in ``FindingsService.list_findings(recorded_after=…)`` and is
    covered in ``test_findings_service.py``.
    """

    def test_posture_records_the_baseline_it_was_assessed_under(self) -> None:
        service = RiskService()
        baseline = datetime.now(timezone.utc)

        posture = service.assess_agent(
            "agent-1", [make_finding("f-1")], baseline_at=baseline
        )

        assert posture.baseline_at == baseline
        # Everything handed to the service is scored: the caller decided eligibility.
        assert posture.finding_count == 1
        assert posture.risk_score == 50

    def test_posture_without_a_baseline_records_none(self) -> None:
        posture = RiskService().assess_agent("agent-1", [make_finding("f-1")])

        assert posture.baseline_at is None

    def test_scoring_ignores_the_deterministic_finding_timestamp(self) -> None:
        """A rule finding carries an epoch timestamp; that must not affect scoring."""
        service = RiskService()
        epoch_finding = make_finding(
            "f-rule", created_at=datetime(1970, 1, 1, tzinfo=timezone.utc)
        )

        posture = service.assess_agent(
            "agent-1", [epoch_finding], baseline_at=datetime.now(timezone.utc)
        )

        assert posture.risk_score == 50
        assert posture.risk_level == RiskLevel.HIGH


class TestScopeIntegrity:
    def test_a_finding_from_another_agent_is_rejected(self) -> None:
        """Rejected, never filtered: a mismatch means the input was assembled wrongly."""
        service = RiskService()

        with pytest.raises(FindingScopeError, match="belongs to agent"):
            service.assess_agent(
                "agent-1",
                [make_finding("f-1"), make_finding("f-2", agent_id="agent-2")],
            )

    def test_a_rejected_assessment_stores_nothing(self) -> None:
        service = RiskService()

        with pytest.raises(FindingScopeError):
            service.assess_agent("agent-1", [make_finding("f-1", agent_id="agent-2")])

        assert service.get_agent_posture("agent-1") is None

    def test_postures_are_isolated_per_agent(self) -> None:
        service = RiskService()

        service.assess_agent("agent-1", [make_finding("f-1", severity=Severity.CRITICAL)])
        quiet = service.assess_agent("agent-2", [])

        assert quiet.risk_level == RiskLevel.LOW
        assert service.get_agent_posture("agent-1").risk_level == RiskLevel.CRITICAL

    def test_clear_removes_postures(self) -> None:
        service = RiskService()
        service.assess_agent("agent-1", [make_finding("f-1")])

        service.clear()

        assert service.get_agent_posture("agent-1") is None
