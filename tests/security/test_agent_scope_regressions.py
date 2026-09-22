"""Agent scope as a security boundary, independent of session semantics.

Two boundaries the platform already enforces and the corpus did not protect. Both
were found by removal experiments during the session semantics review: each could be
deleted from the implementation without a single corpus test objecting, because
**session ownership was masking them**.

    session ownership refuses a foreign agent's request
            │
            └── so cross-agent aggregation never occurs
                    │
                    └── so nothing exercises the agent-scope guards beneath it

That masking is the reason these belong in the corpus now rather than later. Any
future change that relaxes session ownership — and `SESSION-LIFECYCLE` is open
precisely to consider such a change — would expose both boundaries at once, with no
regression in place to notice if one had already been removed.

These tests record existing behaviour. **No new security behaviour is introduced**;
the implementation already enforces both. What changes is that removing either now
fails.

The detectors are exercised directly rather than through the runtime pipeline,
because session ownership would refuse the very requests that would put two agents'
evidence in one place. Testing through the pipeline would assert that ownership
works, which is already covered, rather than that the boundary beneath it does.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.audit_event import Decision
from app.models.finding import Finding, FindingCategory, Severity
from app.models.session_event import SessionEvent
from app.models.watermark import BaselineWatermark
from app.services.agent_risk_aggregate import AgentRiskAggregate
from app.services.detection_service import EXCESSIVE_DENIAL_THRESHOLD, DetectionService
from app.services.risk_aggregator import RiskAggregator


def denial(session_id: str, agent_id: str, offset_seconds: int = 0) -> SessionEvent:
    return SessionEvent(
        session_id=session_id,
        agent_id=agent_id,
        tool_id="unauthorized_tool",
        decision=Decision.DENY,
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=offset_seconds),
    )


def finding_for(agent_id: str, finding_id: str, sequence: int) -> Finding:
    return Finding(
        finding_id=finding_id,
        session_id="shared-session",
        agent_id=agent_id,
        rule_name="PROMPT_INJECTION",
        rule_id="PROMPT_INJECTION",
        severity=Severity.HIGH,
        category=FindingCategory.PROMPT_INJECTION,
        description="scope probe",
        evidence_sequence=sequence,
        recorded_at=datetime.now(timezone.utc),
    )


class TestDenialAggregationIsScopedByAgent:
    """`EXCESSIVE_DENIALS` aggregation is scoped by agent identity.

    The detector partitions on `(session_id, agent_id)`. Dropping `agent_id` from
    that partition previously cost zero corpus failures, so nothing recorded that
    denials from different agents must not accumulate together — which is what
    would let one agent's traffic push another toward a containment threshold if
    they ever shared a session.
    """

    @pytest.mark.security_invariant
    def test_invariant_two_agents_denials_do_not_aggregate(self) -> None:
        """Below threshold individually, at threshold only if wrongly combined."""
        service = DetectionService()
        below = EXCESSIVE_DENIAL_THRESHOLD - 1
        events = [denial("shared-session", "agent-a") for _ in range(below)] + [
            denial("shared-session", "agent-b") for _ in range(below)
        ]
        assert len(events) >= EXCESSIVE_DENIAL_THRESHOLD, "probe must be able to trip"

        findings = service.detect_excessive_denials(events)

        assert findings == []

    @pytest.mark.security_invariant
    def test_invariant_a_finding_is_attributed_to_the_agent_that_earned_it(
        self,
    ) -> None:
        """One agent crossing the threshold must not implicate the other.

        The complement of the test above: aggregation must still work per agent, and
        must name the right one. A partition keyed on the wrong field could suppress
        all findings and satisfy the first test alone.
        """
        service = DetectionService()
        events = [
            denial("shared-session", "agent-a") for _ in range(EXCESSIVE_DENIAL_THRESHOLD)
        ] + [denial("shared-session", "agent-b")]

        findings = service.detect_excessive_denials(events)

        assert len(findings) == 1
        assert findings[0].agent_id == "agent-a"
        assert findings[0].rule_name == "EXCESSIVE_DENIALS"

    @pytest.mark.security_invariant
    def test_invariant_each_agent_crossing_the_threshold_gets_its_own_finding(
        self,
    ) -> None:
        """Two agents, each independently over the line, produce two findings —
        not one merged finding attributed to whichever was seen first."""
        service = DetectionService()
        events = [
            denial("shared-session", agent)
            for agent in ("agent-a", "agent-b")
            for _ in range(EXCESSIVE_DENIAL_THRESHOLD)
        ]

        findings = service.detect_excessive_denials(events)

        assert {f.agent_id for f in findings} == {"agent-a", "agent-b"}
        assert len({f.finding_id for f in findings}) == 2

    @pytest.mark.security_regression
    def test_session_remains_part_of_the_partition(self) -> None:
        """Agent scope is being pinned here, not substituted for session scope.

        One agent's denials spread across two sessions must not combine either —
        that is the M2a accounting control, and a partition keyed on agent alone
        would break it while satisfying every test above.
        """
        service = DetectionService()
        events = [denial("session-1", "agent-a") for _ in range(2)] + [
            denial("session-2", "agent-a") for _ in range(2)
        ]

        assert service.detect_excessive_denials(events) == []


class TestRiskReconstructionIsScopedByAgent:
    """Risk reconstruction cannot consume findings belonging to another agent.

    `AgentRiskAggregate` guards agent scope on both paths — incremental ingestion
    and full rebuild. The rebuild filter previously survived removal with **zero**
    failures, so nothing recorded that reconstructing agent A's posture must ignore
    agent B's evidence.
    """

    @pytest.mark.security_invariant
    def test_invariant_incremental_ingestion_rejects_another_agents_finding(
        self,
    ) -> None:
        """Rejected, not filtered: a mismatch means the caller assembled the
        security input incorrectly, and silently dropping it would hide that."""
        aggregate = AgentRiskAggregate(BaselineWatermark(agent_id="agent-a"))

        with pytest.raises(ValueError, match="Agent mismatch"):
            aggregate.apply_finding(finding_for("agent-b", "f-b", 1))

    @pytest.mark.security_invariant
    def test_invariant_rebuild_ignores_another_agents_findings(self) -> None:
        """The rebuild path filters rather than raises, because reconciliation is
        handed the whole evidence store and must select from it."""
        aggregate = AgentRiskAggregate(BaselineWatermark(agent_id="agent-a"))

        aggregate.rebuild_from_findings(
            [
                finding_for("agent-a", "f-a1", 1),
                finding_for("agent-b", "f-b1", 2),
                finding_for("agent-b", "f-b2", 3),
            ],
            BaselineWatermark(agent_id="agent-a"),
        )

        posture = aggregate.snapshot()
        assert posture.finding_count == 1
        assert posture.agent_id == "agent-a"

    @pytest.mark.security_invariant
    def test_invariant_one_agents_evidence_cannot_move_another_agents_posture(
        self,
    ) -> None:
        """The property the two guards exist for, asserted end to end across the
        aggregator rather than on one aggregate."""
        aggregator = RiskAggregator()
        aggregator.reset_to_baseline(BaselineWatermark(agent_id="agent-a"))
        aggregator.reset_to_baseline(BaselineWatermark(agent_id="agent-b"))
        before = aggregator.get_posture("agent-a")

        aggregator.ingest_finding(finding_for("agent-b", "f-b1", 1))

        after = aggregator.get_posture("agent-a")
        assert after.risk_score == before.risk_score
        assert after.finding_count == before.finding_count == 0
        assert aggregator.get_posture("agent-b").finding_count == 1

    @pytest.mark.security_regression
    def test_the_agents_own_evidence_still_counts(self) -> None:
        """The positive control. Without it, a guard that rejected everything
        would satisfy all three invariants above."""
        aggregate = AgentRiskAggregate(BaselineWatermark(agent_id="agent-a"))

        applied = aggregate.apply_finding(finding_for("agent-a", "f-a1", 1))

        assert applied is True
        assert aggregate.snapshot().finding_count == 1
