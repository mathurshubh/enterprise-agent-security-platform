"""End-to-end contract verification for M5-B (Data Models, Sequencing, and Risk Projection).

Validates:
- Invariants B-1 through B-14 across end-to-end services.
- Complete agent security lifecycle from UNINITIALIZED through HEALTHY, STALE self-healing,
  SUSPENSION, and REINSTATEMENT epoch transition.
- Production dependency injection in app.api.dependencies (RiskAggregator & AgentLockManager wiring).
- Zero legacy RiskService invocation on the HEALTHY authorization hot path.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.api import dependencies
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.agent_risk_posture import PostureState
from app.models.audit_event import Decision
from app.models.finding import FindingStatus, Severity
from app.models.risk_assessment import RiskLevel
from app.models.watermark import UNASSIGNED_SEQUENCE, BaselineWatermark
from app.runtime.execution_authority import ExecutionAuthority
from app.services.agent_lock_manager import AgentLockManager
from app.services.agent_risk_aggregate import AgentRiskAggregate
from app.services.agent_service import AgentService
from app.services.enforcement_coordinator import EnforcementCoordinator
from app.services.findings_service import FindingsService
from app.services.risk_aggregator import RiskAggregator
from app.services.risk_service import RiskService
from app.services.runtime_bootstrap import (
    bootstrap_runtime_service,
    create_default_detection_registry,
)
from app.services.session_service import SessionService
from tests.services.test_findings_service import make_finding


class TestM5BContractInvariantsB1ThroughB14:
    """Explicit tests for all frozen M5-B contract invariants B-1 through B-14."""

    def test_b1_and_b7_projection_equivalence_and_reconstructibility(self) -> None:
        """B-1 & B-7: HEALTHY projection matches deterministic rebuild from authoritative evidence."""
        agent_id = "agent-b1"
        watermark = BaselineWatermark(agent_id=agent_id, baseline_sequence=0)
        aggregate = AgentRiskAggregate(watermark)

        findings = [
            make_finding("f1", agent_id=agent_id, severity=Severity.LOW).model_copy(
                update={"evidence_sequence": 1}
            ),
            make_finding("f2", agent_id=agent_id, severity=Severity.MEDIUM).model_copy(
                update={"evidence_sequence": 2}
            ),
        ]

        # Incremental application
        for f in findings:
            aggregate.apply_finding(f)
        incremental_snapshot = aggregate.snapshot()

        # Full reconstruction
        rebuilt = AgentRiskAggregate(watermark)
        rebuilt.rebuild_from_findings(findings, watermark)
        rebuilt_snapshot = rebuilt.snapshot()

        # Compare security-relevant fields (B-1)
        assert incremental_snapshot.risk_score == rebuilt_snapshot.risk_score == 35  # 10 + 25
        assert incremental_snapshot.risk_level == rebuilt_snapshot.risk_level == RiskLevel.MEDIUM
        assert incremental_snapshot.last_applied_sequence == rebuilt_snapshot.last_applied_sequence == 2
        assert incremental_snapshot.finding_count == rebuilt_snapshot.finding_count == 2
        assert incremental_snapshot.counts_by_severity == rebuilt_snapshot.counts_by_severity
        assert incremental_snapshot.state == rebuilt_snapshot.state == PostureState.HEALTHY

    def test_b2_contiguous_application(self) -> None:
        """B-2: Cursor advances contiguously for every accepted post-baseline finding."""
        agent_id = "agent-b2"
        aggregate = AgentRiskAggregate(BaselineWatermark(agent_id=agent_id, baseline_sequence=0))

        f1 = make_finding("f1", agent_id=agent_id).model_copy(update={"evidence_sequence": 1})
        f2 = make_finding("f2", agent_id=agent_id).model_copy(update={"evidence_sequence": 2})

        assert aggregate.apply_finding(f1) is True
        assert aggregate.last_applied_sequence == 1
        assert aggregate.apply_finding(f2) is True
        assert aggregate.last_applied_sequence == 2

    def test_b3_idempotent_deduplication(self) -> None:
        """B-3: Sequence <= last_applied_sequence is an idempotent no-op."""
        agent_id = "agent-b3"
        aggregate = AgentRiskAggregate(BaselineWatermark(agent_id=agent_id, baseline_sequence=0))

        f1 = make_finding("f1", agent_id=agent_id).model_copy(update={"evidence_sequence": 1})
        aggregate.apply_finding(f1)
        v1 = aggregate.posture_version

        # Re-apply same sequence
        assert aggregate.apply_finding(f1) is False
        assert aggregate.posture_version == v1
        assert aggregate.last_applied_sequence == 1

    def test_b4_fail_closed_on_sequence_gap(self) -> None:
        """B-4: Sequence gap (seq > last_applied + 1) transitions projection to STALE."""
        agent_id = "agent-b4"
        aggregate = AgentRiskAggregate(BaselineWatermark(agent_id=agent_id, baseline_sequence=0))

        f3 = make_finding("f3", agent_id=agent_id).model_copy(update={"evidence_sequence": 3})
        assert aggregate.apply_finding(f3) is False
        assert aggregate.state == PostureState.STALE

    def test_b5_baseline_isolation(self) -> None:
        """B-5: Findings at or before baseline sequence belong to prior epoch and are ignored."""
        agent_id = "agent-b5"
        watermark = BaselineWatermark(agent_id=agent_id, baseline_sequence=5)
        aggregate = AgentRiskAggregate(watermark)

        f4 = make_finding("f4", agent_id=agent_id).model_copy(update={"evidence_sequence": 4})
        f5 = make_finding("f5", agent_id=agent_id).model_copy(update={"evidence_sequence": 5})

        assert aggregate.apply_finding(f4) is False
        assert aggregate.apply_finding(f5) is False
        assert aggregate.last_applied_sequence == 5
        assert aggregate.finding_count == 0

    def test_b6_finite_posture_state_machine(self) -> None:
        """B-6: PostureState consists strictly of UNINITIALIZED, HEALTHY, STALE."""
        assert {s.value for s in PostureState} == {"UNINITIALIZED", "HEALTHY", "STALE"}

    def test_b8_fail_closed_uninitialized_fallback(self) -> None:
        """B-8: Unprojected agent returns fail-closed UNINITIALIZED posture."""
        aggregator = RiskAggregator()
        posture = aggregator.get_posture("unknown-agent")
        assert posture.state == PostureState.UNINITIALIZED
        assert posture.risk_score == 0
        assert posture.risk_level == RiskLevel.LOW

    def test_b9_bounded_hot_state_memory(self) -> None:
        """B-9: Zero finding collections stored in memory; rule counts bounded by vocabulary."""
        agent_id = "agent-b9"
        vocabulary = {"PROMPT_INJECTION", "SENSITIVE_FILE_ACCESS"}
        aggregate = AgentRiskAggregate(
            BaselineWatermark(agent_id=agent_id, baseline_sequence=0),
            rule_vocabulary=vocabulary,
        )

        # Apply finding with unknown rule
        f_arbitrary = make_finding("f-arb", agent_id=agent_id, rule_id="ATTACKER_CONTROLLED_RULE").model_copy(
            update={"evidence_sequence": 1}
        )
        aggregate.apply_finding(f_arbitrary)

        # Rule vocabulary boundary check
        assert "ATTACKER_CONTROLLED_RULE" not in aggregate.counts_by_rule
        # Verify aggregate has no finding ID list
        assert not hasattr(aggregate, "finding_ids")
        assert not hasattr(aggregate, "_findings")

    def test_b10_baseline_boundary_coupling(self) -> None:
        """B-10: BaselineWatermark couples timestamp and sequence as an immutable value."""
        findings_service = FindingsService()
        agent_id = "agent-b10"
        for i in range(1, 4):
            findings_service.record_finding(make_finding(f"f{i}", agent_id=agent_id))

        t = datetime.now(timezone.utc)
        watermark = findings_service.capture_baseline(agent_id=agent_id, baseline_at=t)
        assert watermark.agent_id == agent_id
        assert watermark.baseline_at == t
        assert watermark.baseline_sequence == 3

    def test_b11_cursor_separation_from_active_risk_contribution(self) -> None:
        """B-11: Cursor tracks all findings; risk score tracks strictly active findings."""
        agent_id = "agent-b11"
        aggregate = AgentRiskAggregate(BaselineWatermark(agent_id=agent_id, baseline_sequence=0))

        f1_resolved = make_finding("f1", agent_id=agent_id, status=FindingStatus.RESOLVED, severity=Severity.HIGH).model_copy(
            update={"evidence_sequence": 1}
        )
        f2_active = make_finding("f2", agent_id=agent_id, status=FindingStatus.OPEN, severity=Severity.LOW).model_copy(
            update={"evidence_sequence": 2}
        )

        aggregate.apply_finding(f1_resolved)
        assert aggregate.last_applied_sequence == 1
        assert aggregate.finding_count == 0  # Resolved does NOT contribute to active count
        assert aggregate.risk_score == 0     # Resolved does NOT contribute to score

        aggregate.apply_finding(f2_active)
        assert aggregate.last_applied_sequence == 2
        assert aggregate.finding_count == 1
        assert aggregate.risk_score == 10

    def test_b12_sequence_authority(self) -> None:
        """B-12: FindingsService owns sequence assignment; 0 = UNASSIGNED."""
        findings_service = FindingsService()
        agent_id = "agent-b12"

        f = make_finding("f1", agent_id=agent_id)
        assert f.evidence_sequence == UNASSIGNED_SEQUENCE

        recorded = findings_service.record_new_findings([f])
        assert len(recorded) == 1
        assert recorded[0].evidence_sequence == 1

    def test_b13_evidence_boundary_consistency(self) -> None:
        """B-13: Finding with seq > baseline_seq but recorded_at <= baseline_at triggers STALE."""
        agent_id = "agent-b13"
        t_baseline = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)
        watermark = BaselineWatermark(agent_id=agent_id, baseline_at=t_baseline, baseline_sequence=5)
        aggregate = AgentRiskAggregate(watermark)

        # Anomalous finding: seq 6 (> 5) but recorded_at is in the past (<= t_baseline)
        t_past = datetime(2026, 9, 21, 11, 0, 0, tzinfo=timezone.utc)
        anomalous = make_finding("f-ano", agent_id=agent_id).model_copy(
            update={"evidence_sequence": 6, "recorded_at": t_past}
        )

        assert aggregate.apply_finding(anomalous) is False
        assert aggregate.state == PostureState.STALE

    def test_b14_idempotent_pre_m5_bootstrap(self) -> None:
        """B-14: FindingsService assigns monotonic sequences during bootstrap for legacy findings."""
        legacy_findings = [
            make_finding("leg-1", agent_id="agent-b14"),
            make_finding("leg-2", agent_id="agent-b14"),
        ]
        service = FindingsService(initial_findings=legacy_findings)
        assert service.get_agent_sequence("agent-b14") == 2
        all_f = service.list_findings(agent_id="agent-b14")
        assert [f.evidence_sequence for f in all_f] == [1, 2]


class TestCompleteM5BLifecycleE2E:
    """Tests the full lifecycle of an agent from uninitialized to suspension and reinstatement."""

    def test_full_agent_lifecycle(self) -> None:
        """Execute the complete M5-B lifecycle end-to-end:

        NEW AGENT
           ↓
        UNINITIALIZED
           ↓
        lazy reconciliation
           ↓
        HEALTHY
           ↓
        incremental findings
           ↓
        HEALTHY
           ↓
        gap / projection failure
           ↓
        STALE
           ↓
        reconciliation
           ↓
        HEALTHY
           ↓
        SUSPEND (due to threshold crossing)
           ↓
        REINSTATE
           ↓
        new baseline epoch
        """
        agent_id = "lifecycle-agent"
        agent_service = AgentService()
        agent_service.register_agent(
            Agent(
                agent_id=agent_id,
                name="Lifecycle Agent",
                owner="security",
                risk_tier=RiskTier.HIGH,
                approved_tools=["file_read"],
                status=AgentStatus.ACTIVE,
            )
        )

        findings_service = FindingsService()
        risk_service = RiskService()
        risk_aggregator = RiskAggregator()
        lock_manager = AgentLockManager()
        execution_authority = ExecutionAuthority()

        runtime = bootstrap_runtime_service(
            agent_service=agent_service,
            session_service=SessionService(),
            audit_service=MagicMock(),
            detection_registry=create_default_detection_registry(),
            agent_id=agent_id,
            findings_service=findings_service,
            risk_service=risk_service,
            execution_authority=execution_authority,
            risk_aggregator=risk_aggregator,
            lock_manager=lock_manager,
        )

        coordinator = EnforcementCoordinator(
            agent_service=agent_service,
            execution_authority=execution_authority,
            findings_service=findings_service,
            risk_aggregator=risk_aggregator,
            lock_manager=lock_manager,
        )

        # 1. NEW AGENT -> UNINITIALIZED
        assert risk_aggregator.get_posture(agent_id).state == PostureState.UNINITIALIZED

        # 2. Lazy reconciliation -> HEALTHY
        posture = runtime._assess_agent_posture(agent_id)
        assert posture.state == PostureState.HEALTHY
        assert posture.finding_count == 0
        assert posture.risk_score == 0

        # 3. Incremental findings -> HEALTHY with active score
        with lock_manager.get_lock(agent_id):
            f1 = make_finding("f1", agent_id=agent_id, severity=Severity.MEDIUM)
            recs = findings_service.record_new_findings([f1])
            for f in recs:
                risk_aggregator.ingest_finding(f)

        posture = runtime._assess_agent_posture(agent_id)
        assert posture.state == PostureState.HEALTHY
        assert posture.last_applied_sequence == 1
        assert posture.risk_score == 25

        # 4. Gap / projection failure -> STALE
        risk_aggregator.mark_stale(agent_id)
        assert risk_aggregator.get_posture(agent_id).state == PostureState.STALE

        # 5. Reconciliation -> restores HEALTHY
        posture = runtime._assess_agent_posture(agent_id)
        assert posture.state == PostureState.HEALTHY
        assert posture.last_applied_sequence == 1
        assert posture.risk_score == 25

        # 6. Add critical finding crossing containment threshold (score 25 + 100 = 125 >= 100)
        with lock_manager.get_lock(agent_id):
            f2 = make_finding("f2", agent_id=agent_id, severity=Severity.CRITICAL)
            recs = findings_service.record_new_findings([f2])
            for f in recs:
                risk_aggregator.ingest_finding(f)

        # 7. Execute request -> triggers SUSPENSION
        result = runtime.execute(
            session_id="crit-sess",
            agent_id=agent_id,
            tool_id="file_read",
            resource="notes.txt",
        )
        assert result.event.decision == Decision.DENY
        assert agent_service.get_agent(agent_id).status == AgentStatus.SUSPENDED
        assert execution_authority.issuance_suspended(agent_id) is True

        # 8. Administrative Reinstatement -> establishes new baseline epoch
        reinstated_agent = coordinator.reinstate(agent_id, actor="sec-admin", reason="remediated")
        assert reinstated_agent.status == AgentStatus.ACTIVE
        assert execution_authority.issuance_suspended(agent_id) is False

        # 9. Invariant: projection is reset to new baseline epoch
        new_posture = risk_aggregator.get_posture(agent_id)
        assert new_posture.state == PostureState.HEALTHY
        assert new_posture.baseline_sequence == 2
        assert new_posture.last_applied_sequence == 2
        assert new_posture.finding_count == 0
        assert new_posture.risk_score == 0


class TestProductionDependencyWiring:
    """Verifies that production dependency wiring always uses RiskAggregator and AgentLockManager."""

    def test_production_singletons_wired_consistently(self) -> None:
        """Production RuntimeService and EnforcementCoordinator share the exact same RiskAggregator and AgentLockManager."""
        assert dependencies.risk_aggregator is not None
        assert dependencies.agent_lock_manager is not None

        # Verify RuntimeService has RiskAggregator and shared AgentLockManager
        assert dependencies.runtime_service._risk_aggregator is dependencies.risk_aggregator
        assert dependencies.runtime_service._lock_manager is dependencies.agent_lock_manager

        # Verify EnforcementCoordinator has RiskAggregator and shared AgentLockManager
        assert dependencies.enforcement_coordinator._risk_aggregator is dependencies.risk_aggregator
        assert dependencies.enforcement_coordinator._lock_manager is dependencies.agent_lock_manager

    def test_healthy_authorization_path_never_invokes_legacy_risk_service(self) -> None:
        """When RiskAggregator is wired and posture is HEALTHY, assess_agent is never called."""
        runtime = dependencies.runtime_service
        agent_id = "agent-1"

        # Ensure agent has a HEALTHY projection
        dependencies.risk_aggregator.reset_to_baseline(
            BaselineWatermark(agent_id=agent_id, baseline_sequence=0)
        )
        assert dependencies.risk_aggregator.get_posture(agent_id).state == PostureState.HEALTHY

        # Mock assess_agent on legacy risk_service
        legacy_spy = MagicMock(side_effect=AssertionError("Legacy risk_service.assess_agent must not be called!"))
        original_assess_agent = runtime._risk_service.assess_agent
        runtime._risk_service.assess_agent = legacy_spy

        try:
            posture = runtime._assess_agent_posture(agent_id)
            assert posture.state == PostureState.HEALTHY
            assert legacy_spy.call_count == 0
        finally:
            runtime._risk_service.assess_agent = original_assess_agent
