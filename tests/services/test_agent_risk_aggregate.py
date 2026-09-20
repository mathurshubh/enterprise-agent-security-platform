"""Unit tests for AgentRiskAggregate projection engine (M5-B).

Validates:
- Invariants B-1 through B-5, B-7, B-9, B-11, B-13
- Separation of evidence frontier cursor from active risk contribution
- Idempotent deduplication and fail-closed gap detection
- Bounded memory and finite rule vocabulary
- Exact M5-A scoring semantics (10/25/50/100, unbounded integer)
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.agent_risk_posture import PostureState
from app.models.finding import Finding, FindingCategory, FindingStatus, Severity
from app.models.risk_assessment import RiskLevel
from app.models.watermark import BaselineWatermark
from app.services.agent_risk_aggregate import (
    DEFAULT_RULE_VOCABULARY,
    AgentRiskAggregate,
)


def make_test_finding(
    finding_id: str,
    agent_id: str = "agent-1",
    severity: Severity = Severity.HIGH,
    status: FindingStatus = FindingStatus.OPEN,
    rule_id: str = "PROMPT_INJECTION",
    evidence_sequence: int = 1,
    recorded_at: datetime | None = None,
) -> Finding:
    t = recorded_at or datetime.now(timezone.utc)
    return Finding(
        finding_id=finding_id,
        session_id="session-1",
        agent_id=agent_id,
        rule_name=rule_id,
        rule_id=rule_id,
        severity=severity,
        category=FindingCategory.PROMPT_INJECTION,
        status=status,
        description="test finding",
        evidence_sequence=evidence_sequence,
        created_at=t,
        recorded_at=t,
    )


class TestAgentRiskAggregate:
    def test_b1_projection_equivalence(self) -> None:
        """Incremental projection matches fresh rebuild for all security-relevant fields (B-1)."""
        t0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
        wm = BaselineWatermark(agent_id="agent-1", baseline_at=t0, baseline_sequence=0)

        agg = AgentRiskAggregate(wm)

        f1 = make_test_finding(
            "f-1", severity=Severity.LOW, evidence_sequence=1,
            recorded_at=t0 + timedelta(seconds=10)
        )
        f2 = make_test_finding(
            "f-2", severity=Severity.MEDIUM, status=FindingStatus.RESOLVED, evidence_sequence=2,
            recorded_at=t0 + timedelta(seconds=20)
        )
        f3 = make_test_finding(
            "f-3", severity=Severity.HIGH, evidence_sequence=3,
            recorded_at=t0 + timedelta(seconds=30)
        )

        assert agg.apply_finding(f1) is True
        assert agg.apply_finding(f2) is True
        assert agg.apply_finding(f3) is True

        incremental_snapshot = agg.snapshot()

        # Rebuild from scratch
        rebuilt = AgentRiskAggregate(wm)
        rebuilt.rebuild_from_findings([f1, f2, f3], wm)
        rebuilt_snapshot = rebuilt.snapshot()

        # Security-relevant fields must match exactly
        assert incremental_snapshot.risk_score == rebuilt_snapshot.risk_score
        assert incremental_snapshot.risk_level == rebuilt_snapshot.risk_level
        assert incremental_snapshot.finding_count == rebuilt_snapshot.finding_count
        assert incremental_snapshot.counts_by_severity == rebuilt_snapshot.counts_by_severity
        assert incremental_snapshot.counts_by_rule == rebuilt_snapshot.counts_by_rule
        assert incremental_snapshot.last_applied_sequence == rebuilt_snapshot.last_applied_sequence
        assert incremental_snapshot.baseline_sequence == rebuilt_snapshot.baseline_sequence
        assert incremental_snapshot.state == PostureState.HEALTHY

    def test_b2_and_b11_cursor_vs_active_contribution(self) -> None:
        """Inactive findings advance sequence cursor without inflating risk score (B-2, B-11)."""
        t0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
        wm = BaselineWatermark(agent_id="agent-1", baseline_at=t0, baseline_sequence=0)
        agg = AgentRiskAggregate(wm)

        # F1: OPEN HIGH -> +50 score, cursor=1
        f1 = make_test_finding(
            "f-1", severity=Severity.HIGH, status=FindingStatus.OPEN, evidence_sequence=1,
            recorded_at=t0 + timedelta(seconds=1)
        )
        assert agg.apply_finding(f1) is True
        assert agg.risk_score == 50
        assert agg.last_applied_sequence == 1
        assert agg.finding_count == 1

        # F2: RESOLVED CRITICAL -> score unchanged (+0), cursor advances to 2
        f2 = make_test_finding(
            "f-2", severity=Severity.CRITICAL, status=FindingStatus.RESOLVED, evidence_sequence=2,
            recorded_at=t0 + timedelta(seconds=2)
        )
        assert agg.apply_finding(f2) is True
        assert agg.risk_score == 50
        assert agg.last_applied_sequence == 2
        assert agg.finding_count == 1
        assert agg.counts_by_severity[Severity.CRITICAL] == 0

        # F3: FALSE_POSITIVE MEDIUM -> score unchanged (+0), cursor advances to 3
        f3 = make_test_finding(
            "f-3", severity=Severity.MEDIUM, status=FindingStatus.FALSE_POSITIVE, evidence_sequence=3,
            recorded_at=t0 + timedelta(seconds=3)
        )
        assert agg.apply_finding(f3) is True
        assert agg.risk_score == 50
        assert agg.last_applied_sequence == 3
        assert agg.finding_count == 1

    def test_b3_idempotent_deduplication(self) -> None:
        """Already applied sequence is safely ignored without mutating posture (B-3)."""
        t0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
        wm = BaselineWatermark(agent_id="agent-1", baseline_at=t0, baseline_sequence=0)
        agg = AgentRiskAggregate(wm)

        f1 = make_test_finding(
            "f-1", severity=Severity.HIGH, evidence_sequence=1,
            recorded_at=t0 + timedelta(seconds=1)
        )
        assert agg.apply_finding(f1) is True
        v1 = agg.posture_version
        score1 = agg.risk_score

        # Duplicate presentation with older sequence
        assert agg.apply_finding(f1) is False
        assert agg.posture_version == v1
        assert agg.risk_score == score1
        assert agg.state == PostureState.HEALTHY

    def test_b4_fail_closed_on_sequence_gap(self) -> None:
        """Sequence gap transitions posture state to STALE and rejects update (B-4)."""
        t0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
        wm = BaselineWatermark(agent_id="agent-1", baseline_at=t0, baseline_sequence=0)
        agg = AgentRiskAggregate(wm)

        f1 = make_test_finding(
            "f-1", severity=Severity.HIGH, evidence_sequence=1,
            recorded_at=t0 + timedelta(seconds=1)
        )
        assert agg.apply_finding(f1) is True

        # Gap: arrival of sequence 3 when expected is 2
        f3 = make_test_finding(
            "f-3", severity=Severity.HIGH, evidence_sequence=3,
            recorded_at=t0 + timedelta(seconds=2)
        )
        assert agg.apply_finding(f3) is False
        assert agg.state == PostureState.STALE
        assert agg.last_applied_sequence == 1  # cursor not advanced on gap

    def test_b5_baseline_isolation(self) -> None:
        """Findings belonging to prior baseline epoch are excluded (B-5)."""
        t0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
        wm = BaselineWatermark(agent_id="agent-1", baseline_at=t0, baseline_sequence=5)
        agg = AgentRiskAggregate(wm)

        # Finding with sequence 4 (pre-baseline)
        f_old = make_test_finding(
            "f-old", severity=Severity.CRITICAL, evidence_sequence=4,
            recorded_at=t0 - timedelta(seconds=10)
        )
        assert agg.apply_finding(f_old) is False
        assert agg.risk_score == 0
        assert agg.last_applied_sequence == 5

    def test_b9_bounded_rule_vocabulary_and_memory(self) -> None:
        """counts_by_rule is bounded by registered vocabulary; no finding objects retained (B-9)."""
        t0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
        wm = BaselineWatermark(agent_id="agent-1", baseline_at=t0, baseline_sequence=0)
        agg = AgentRiskAggregate(wm)

        # Ingest 100 findings with arbitrary unregistered rule IDs
        for i in range(1, 101):
            f = make_test_finding(
                f"f-{i}",
                severity=Severity.LOW,
                rule_id=f"ARBITRARY_UNREGISTERED_RULE_{i}",
                evidence_sequence=i,
                recorded_at=t0 + timedelta(seconds=i),
            )
            assert agg.apply_finding(f) is True

        # Assert architectural bounds:
        # 1. counts_by_rule must NOT contain arbitrary rule IDs
        assert len(agg.counts_by_rule) <= len(DEFAULT_RULE_VOCABULARY)
        assert len(agg.counts_by_rule) == 0  # none of the arbitrary rules were in vocabulary

        # 2. Risk score and counts still accumulate accurately
        assert agg.finding_count == 100
        assert agg.counts_by_severity[Severity.LOW] == 100
        assert agg.risk_score == 1000  # 100 * 10

        # 3. No collection of finding objects or IDs stored on the aggregate
        assert not hasattr(agg, "_applied_findings")
        assert not hasattr(agg, "_finding_ids")
        assert not hasattr(agg, "_finding_objects")

    def test_b10_reset_to_baseline(self) -> None:
        """reset_to_baseline resets active risk state and snaps cursor to watermark (B-10)."""
        t0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
        wm0 = BaselineWatermark(agent_id="agent-1", baseline_at=t0, baseline_sequence=0)
        agg = AgentRiskAggregate(wm0)

        f1 = make_test_finding("f-1", severity=Severity.CRITICAL, evidence_sequence=1, recorded_at=t0 + timedelta(seconds=1))
        f2 = make_test_finding("f-2", severity=Severity.HIGH, evidence_sequence=2, recorded_at=t0 + timedelta(seconds=2))
        agg.apply_finding(f1)
        agg.apply_finding(f2)
        assert agg.risk_score == 150

        # Reinstatement establishes new baseline watermark
        t1 = datetime(2026, 9, 20, 11, 0, 0, tzinfo=timezone.utc)
        wm1 = BaselineWatermark(agent_id="agent-1", baseline_at=t1, baseline_sequence=2)
        agg.reset_to_baseline(wm1)

        assert agg.risk_score == 0
        assert agg.risk_level == RiskLevel.LOW
        assert agg.finding_count == 0
        assert agg.last_applied_sequence == 2
        assert agg.baseline_sequence == 2
        assert agg.state == PostureState.HEALTHY

    def test_b13_evidence_boundary_consistency_anomaly(self) -> None:
        """Finding with sequence > baseline_sequence but recorded_at <= baseline_at triggers STALE (B-13)."""
        t_base = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
        wm = BaselineWatermark(agent_id="agent-1", baseline_at=t_base, baseline_sequence=5)
        agg = AgentRiskAggregate(wm)

        # Inconsistent finding: seq=6 (post-baseline) but recorded_at is prior to baseline_at!
        f_inconsistent = make_test_finding(
            "f-bad",
            evidence_sequence=6,
            recorded_at=t_base - timedelta(seconds=5),  # <= baseline_at!
        )
        assert agg.apply_finding(f_inconsistent) is False
        assert agg.state == PostureState.STALE
        assert agg.last_applied_sequence == 5  # cursor does not advance on anomaly

    def test_m5_a_scoring_semantics_exact_weights(self) -> None:
        """Scoring uses exact additive 10/25/50/100 weights and unbounded integer scores."""
        t0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)
        wm = BaselineWatermark(agent_id="agent-1", baseline_at=t0, baseline_sequence=0)
        agg = AgentRiskAggregate(wm)

        # 1. LOW = 10 -> score 10, LOW
        agg.apply_finding(make_test_finding("f-1", severity=Severity.LOW, evidence_sequence=1, recorded_at=t0 + timedelta(seconds=1)))
        assert agg.risk_score == 10
        assert agg.risk_level == RiskLevel.LOW

        # 2. MEDIUM = 25 -> 10 + 25 = 35 -> score 35, MEDIUM
        agg.apply_finding(make_test_finding("f-2", severity=Severity.MEDIUM, evidence_sequence=2, recorded_at=t0 + timedelta(seconds=2)))
        assert agg.risk_score == 35
        assert agg.risk_level == RiskLevel.MEDIUM

        # 3. HIGH = 50 -> 35 + 50 = 85 -> score 85, HIGH
        agg.apply_finding(make_test_finding("f-3", severity=Severity.HIGH, evidence_sequence=3, recorded_at=t0 + timedelta(seconds=3)))
        assert agg.risk_score == 85
        assert agg.risk_level == RiskLevel.HIGH

        # 4. CRITICAL = 100 -> 85 + 100 = 185 -> score 185, CRITICAL (unbounded)
        agg.apply_finding(make_test_finding("f-4", severity=Severity.CRITICAL, evidence_sequence=4, recorded_at=t0 + timedelta(seconds=4)))
        assert agg.risk_score == 185
        assert agg.risk_level == RiskLevel.CRITICAL

    def test_agent_mismatch_and_unassigned_sequence_errors(self) -> None:
        """apply_finding rejects agent mismatch and unassigned sequence."""
        wm = BaselineWatermark(agent_id="agent-1", baseline_at=None, baseline_sequence=0)
        agg = AgentRiskAggregate(wm)

        f_other = make_test_finding("f-other", agent_id="agent-2", evidence_sequence=1)
        with pytest.raises(ValueError, match="Agent mismatch"):
            agg.apply_finding(f_other)

        f_unassigned = make_test_finding("f-unassigned", agent_id="agent-1", evidence_sequence=0)
        with pytest.raises(ValueError, match="Cannot apply unassigned finding"):
            agg.apply_finding(f_unassigned)
