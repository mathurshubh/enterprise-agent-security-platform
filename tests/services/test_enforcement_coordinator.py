"""Administrative recovery from containment (M2b Step 5).

Reinstatement spans two independent stores, so the contract is convergence rather than
atomicity:

    success      → ACTIVE + issuance open
    partial      → ACTIVE + issuance closed   (fail-closed, surfaced, repairable)
    retry        → ACTIVE + issuance open

and, throughout, no runtime path may recover a contained agent.
"""

import inspect

import pytest

import app.services.runtime_service as runtime_service_module
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import Decision
from app.models.execution_binding import ExecutionBinding
from app.runtime.execution_authority import ExecutionAuthority
from app.services.agent_service import (
    AgentNotFoundError,
    AgentNotSuspendedError,
    AgentService,
)
from app.services.enforcement_coordinator import (
    EnforcementCoordinator,
    ReinstatementIncompleteError,
)
from app.services.findings_service import FindingsService
from tests.conftest import create_test_agent_service
from tests.services.test_findings_service import make_finding

AGENT_ID = "contained-agent"
BINDING = ExecutionBinding.from_operation("file_read", {"path": "notes.txt"})


class RefusingAuthority(ExecutionAuthority):
    """An authority whose gate cannot be reopened, to exercise partial failure."""

    def __init__(self) -> None:
        super().__init__()
        self.repair_allowed = False

    def resume_issuance(self, agent_id: str) -> None:
        if not self.repair_allowed:
            return  # silently fails to reopen
        super().resume_issuance(agent_id)


def build(authority: ExecutionAuthority | None = None):
    agents = create_test_agent_service()
    agents.register_agent(
        Agent(
            agent_id=AGENT_ID,
            name="Contained",
            owner="security-team",
            risk_tier=RiskTier.HIGH,
            approved_tools=["file_read"],
            status=AgentStatus.ACTIVE,
        )
    )
    authority = authority or ExecutionAuthority()
    return agents, authority, EnforcementCoordinator(agents, authority)


def contain(
    agents: AgentService,
    authority: ExecutionAuthority,
    agent_id: str = AGENT_ID,
) -> None:
    """Reproduce what the runtime does when it contains an agent."""
    authority.suspend_issuance(agent_id)
    agents.suspend_agent(agent_id, reason="critical risk posture")


class TestSuccessfulReinstatement:
    def test_agent_returns_to_service_with_issuance_open(self) -> None:
        agents, authority, coordinator = build()
        contain(agents, authority)

        agent = coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        assert agent.status == AgentStatus.ACTIVE
        assert authority.issuance_suspended(AGENT_ID) is False
        assert authority.issue(BINDING, Decision.ALLOW, agent_id=AGENT_ID) is not None

    def test_reinstatement_is_attributed(self) -> None:
        agents, authority, coordinator = build()
        contain(agents, authority)

        coordinator.reinstate(AGENT_ID, actor="admin-1", reason="false positive")

        transition = agents.list_transitions(AGENT_ID)[-1]
        assert transition.actor == "admin-1"
        assert transition.reason == "false positive"

    def test_grants_revoked_during_containment_stay_revoked(self) -> None:
        agents, authority, coordinator = build()
        revoked = authority.issue(BINDING, Decision.ALLOW, agent_id=AGENT_ID)
        contain(agents, authority)

        coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        from app.runtime.execution_authority import (
            ExecutionBindingError,
            ExecutionRefusalReason,
        )

        with pytest.raises(ExecutionBindingError) as refusal:
            authority.verify_and_consume(revoked, BINDING)
        assert refusal.value.reason == ExecutionRefusalReason.REVOKED


class TestRefusedReinstatement:
    def test_an_unknown_agent_is_refused(self) -> None:
        _, _, coordinator = build()

        with pytest.raises(AgentNotFoundError):
            coordinator.reinstate("absent", actor="admin-1", reason="investigated")

    def test_an_active_agent_is_refused(self) -> None:
        _, authority, coordinator = build()

        with pytest.raises(AgentNotSuspendedError):
            coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        assert authority.issuance_suspended(AGENT_ID) is False

    @pytest.mark.parametrize(("actor", "reason"), [("", "why"), ("admin-1", "  ")])
    def test_reinstatement_must_be_attributed(self, actor: str, reason: str) -> None:
        agents, authority, coordinator = build()
        contain(agents, authority)

        with pytest.raises(ValueError):
            coordinator.reinstate(AGENT_ID, actor=actor, reason=reason)

        # The refusal changed nothing: containment still holds.
        assert agents.get_agent(AGENT_ID).status == AgentStatus.SUSPENDED
        assert authority.issuance_suspended(AGENT_ID) is True


class TestPartialFailureConverges:
    def test_a_failed_gate_reopen_is_surfaced_not_reported_as_success(self) -> None:
        authority = RefusingAuthority()
        agents, authority, coordinator = build(authority)
        contain(agents, authority)

        with pytest.raises(ReinstatementIncompleteError):
            coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

    def test_the_partial_state_is_fail_closed(self) -> None:
        authority = RefusingAuthority()
        agents, authority, coordinator = build(authority)
        contain(agents, authority)

        with pytest.raises(ReinstatementIncompleteError):
            coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        # Active to policy, but no execution authority can be obtained.
        assert agents.get_agent(AGENT_ID).status == AgentStatus.ACTIVE
        assert authority.issuance_suspended(AGENT_ID) is True
        assert authority.issue(BINDING, Decision.ALLOW, agent_id=AGENT_ID) is None

    def test_retry_repairs_the_asymmetry(self) -> None:
        authority = RefusingAuthority()
        agents, authority, coordinator = build(authority)
        contain(agents, authority)
        with pytest.raises(ReinstatementIncompleteError):
            coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        authority.repair_allowed = True
        repaired = coordinator.repair(AGENT_ID)

        assert repaired.status == AgentStatus.ACTIVE
        assert authority.issuance_suspended(AGENT_ID) is False
        assert authority.issue(BINDING, Decision.ALLOW, agent_id=AGENT_ID) is not None

    def test_repair_cannot_recover_a_suspended_agent(self) -> None:
        """Repair reopens a gate; it is not a second route out of containment."""
        agents, authority, coordinator = build()
        contain(agents, authority)

        with pytest.raises(ReinstatementIncompleteError):
            coordinator.repair(AGENT_ID)

        assert agents.get_agent(AGENT_ID).status == AgentStatus.SUSPENDED
        assert authority.issuance_suspended(AGENT_ID) is True


class TestRuntimeCannotRecover:
    def test_no_runtime_path_reinstates_or_reopens_issuance(self) -> None:
        """Runtime enforcement is one-way: containment yes, recovery no."""
        source = inspect.getsource(runtime_service_module)

        assert "reinstate" not in source
        assert "resume_issuance" not in source

    def test_the_coordinator_never_contains(self) -> None:
        import app.services.enforcement_coordinator as coordinator_module

        source = inspect.getsource(coordinator_module)

        assert "suspend_agent" not in source
        assert "suspend_issuance" not in source


class TestEnforcementBaselineIntegration:
    """Validates enforcement baseline watermark coupling, persistence, and non-recomputation (B-10)."""

    def test_first_time_agent_baseline_semantics(self) -> None:
        """First-time agent has None baseline_at and 0 baseline_sequence."""
        agents = create_test_agent_service()
        agents.register_agent(
            Agent(
                agent_id="fresh-agent",
                name="Fresh",
                owner="security",
                risk_tier=RiskTier.LOW,
                approved_tools=["file_read"],
                status=AgentStatus.ACTIVE,
            )
        )
        state = agents.get_enforcement_state("fresh-agent")
        assert state.enforcement_baseline_at is None
        assert state.enforcement_baseline_sequence == 0

        baseline = agents.get_current_baseline("fresh-agent")
        assert baseline.agent_id == "fresh-agent"
        assert baseline.baseline_at is None
        assert baseline.baseline_sequence == 0

    def test_reinstatement_persists_timestamp_and_sequence(self) -> None:
        """EnforcementCoordinator.reinstate persists exact watermark timestamp and sequence."""
        agents = create_test_agent_service()
        authority = ExecutionAuthority()
        findings = FindingsService()
        coordinator = EnforcementCoordinator(agents, authority, findings)

        agents.register_agent(
            Agent(
                agent_id=AGENT_ID,
                name="Contained",
                owner="security",
                risk_tier=RiskTier.HIGH,
                approved_tools=["file_read"],
                status=AgentStatus.ACTIVE,
            )
        )
        # Record findings before containment
        f1 = findings.record_finding(make_finding("f-1", agent_id=AGENT_ID))
        f2 = findings.record_finding(make_finding("f-2", agent_id=AGENT_ID))
        assert f1.evidence_sequence == 1
        assert f2.evidence_sequence == 2

        contain(agents, authority)
        coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        state = agents.get_enforcement_state(AGENT_ID)
        assert state.enforcement_baseline_at is not None
        assert state.enforcement_baseline_sequence == 2

        baseline = agents.get_current_baseline(AGENT_ID)
        assert baseline.baseline_at == state.enforcement_baseline_at
        assert baseline.baseline_sequence == 2

    def test_current_baseline_does_not_recompute_after_new_findings(self) -> None:
        """Adding new findings after reinstatement does not mutate stored baseline watermark."""
        from tests.services.test_findings_service import make_finding

        agents = create_test_agent_service()
        authority = ExecutionAuthority()
        findings = FindingsService()
        coordinator = EnforcementCoordinator(agents, authority, findings)

        agents.register_agent(
            Agent(
                agent_id=AGENT_ID,
                name="Contained",
                owner="security",
                risk_tier=RiskTier.HIGH,
                approved_tools=["file_read"],
                status=AgentStatus.ACTIVE,
            )
        )
        for i in range(1, 11):
            findings.record_finding(make_finding(f"f-pre-{i}", agent_id=AGENT_ID))
        assert findings.get_agent_sequence(AGENT_ID) == 10

        contain(agents, authority)
        coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        baseline_before = agents.get_current_baseline(AGENT_ID)
        assert baseline_before.baseline_sequence == 10

        # Record findings after reinstatement: 11, 12, 13
        findings.record_finding(make_finding("f-post-11", agent_id=AGENT_ID))
        findings.record_finding(make_finding("f-post-12", agent_id=AGENT_ID))
        findings.record_finding(make_finding("f-post-13", agent_id=AGENT_ID))
        assert findings.get_agent_sequence(AGENT_ID) == 13

        # get_current_baseline MUST still return sequence 10, never recompute to 13
        baseline_after = agents.get_current_baseline(AGENT_ID)
        assert baseline_after.baseline_sequence == 10
        assert baseline_after.baseline_at == baseline_before.baseline_at

    def test_failed_persistence_does_not_reopen_issuance(self) -> None:
        """If agent reinstatement fails, issuance is not reopened and remains suspended."""
        agents = create_test_agent_service()
        authority = ExecutionAuthority()
        coordinator = EnforcementCoordinator(agents, authority)

        # Agent is not registered, so reinstate_agent will raise AgentNotFoundError
        authority.suspend_issuance("unregistered-agent")

        with pytest.raises(AgentNotFoundError):
            coordinator.reinstate("unregistered-agent", actor="admin", reason="retry")

        assert authority.issuance_suspended("unregistered-agent") is True


class TestEnforcementCoordinatorRiskAggregatorIntegration:
    """Verifies that EnforcementCoordinator synchronizes with RiskAggregator (M5-B Step 7)."""

    def test_reinstate_resets_risk_aggregator_projection(self) -> None:
        """Successful reinstatement resets projection to the newly captured baseline."""
        from app.models.agent_risk_posture import PostureState
        from app.services.agent_lock_manager import AgentLockManager
        from app.services.risk_aggregator import RiskAggregator

        agents = create_test_agent_service()
        authority = ExecutionAuthority()
        findings = FindingsService()
        aggregator = RiskAggregator()
        lock_mgr = AgentLockManager()

        coordinator = EnforcementCoordinator(
            agents,
            authority,
            findings,
            risk_aggregator=aggregator,
            lock_manager=lock_mgr,
        )

        agents.register_agent(
            Agent(
                agent_id=AGENT_ID,
                name="Contained",
                owner="security",
                risk_tier=RiskTier.HIGH,
                approved_tools=["file_read"],
                status=AgentStatus.ACTIVE,
            )
        )

        # Add pre-containment findings
        for i in range(1, 4):
            findings.record_finding(make_finding(f"f-{i}", agent_id=AGENT_ID))

        contain(agents, authority)
        coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        # Posture in aggregator must be HEALTHY, reset to baseline seq 3 with 0 findings
        posture = aggregator.get_posture(AGENT_ID)
        assert posture.state == PostureState.HEALTHY
        assert posture.baseline_sequence == 3
        assert posture.last_applied_sequence == 3
        assert posture.finding_count == 0
        assert posture.risk_score == 0
        assert authority.issuance_suspended(AGENT_ID) is False

    def test_reinstatement_failure_when_projection_reset_fails_keeps_issuance_suspended(
        self,
    ) -> None:
        """If RiskAggregator.reset_to_baseline fails, issuance gate remains CLOSED."""
        from unittest.mock import MagicMock

        from app.services.agent_lock_manager import AgentLockManager
        from app.services.risk_aggregator import RiskAggregator

        agents = create_test_agent_service()
        authority = ExecutionAuthority()
        findings = FindingsService()
        aggregator = RiskAggregator()
        lock_mgr = AgentLockManager()

        # Fault injection: projection reset fails
        aggregator.reset_to_baseline = MagicMock(
            side_effect=RuntimeError("Projection engine failure")
        )

        coordinator = EnforcementCoordinator(
            agents,
            authority,
            findings,
            risk_aggregator=aggregator,
            lock_manager=lock_mgr,
        )

        agents.register_agent(
            Agent(
                agent_id=AGENT_ID,
                name="Contained",
                owner="security",
                risk_tier=RiskTier.HIGH,
                approved_tools=["file_read"],
                status=AgentStatus.ACTIVE,
            )
        )

        contain(agents, authority)
        assert authority.issuance_suspended(AGENT_ID) is True

        with pytest.raises(RuntimeError, match="Projection engine failure"):
            coordinator.reinstate(AGENT_ID, actor="admin-1", reason="investigated")

        # Invariant: issuance MUST remain suspended (fail-closed convergence)
        assert authority.issuance_suspended(AGENT_ID) is True

    def test_repair_resets_projection_and_reopens_issuance(self) -> None:
        """Repair path resets projection to stored baseline before reopening issuance."""
        from app.models.agent_risk_posture import PostureState
        from app.services.agent_lock_manager import AgentLockManager
        from app.services.risk_aggregator import RiskAggregator

        agents = create_test_agent_service()
        authority = ExecutionAuthority()
        aggregator = RiskAggregator()
        lock_mgr = AgentLockManager()

        coordinator = EnforcementCoordinator(
            agents,
            authority,
            risk_aggregator=aggregator,
            lock_manager=lock_mgr,
        )

        agents.register_agent(
            Agent(
                agent_id=AGENT_ID,
                name="Contained",
                owner="security",
                risk_tier=RiskTier.HIGH,
                approved_tools=["file_read"],
                status=AgentStatus.ACTIVE,
            )
        )

        # Simulate authority still suspended for ACTIVE agent
        authority.suspend_issuance(AGENT_ID)

        repaired = coordinator.repair(AGENT_ID)
        assert repaired.status == AgentStatus.ACTIVE
        assert authority.issuance_suspended(AGENT_ID) is False
        assert aggregator.get_posture(AGENT_ID).state == PostureState.HEALTHY


class TestProjectionFailureHandling:
    """Projection failure behavior: FindingsService is authoritative; failed projection is STALE (not rolled back)."""

    def test_ingest_failure_marks_stale_without_rolling_back_evidence(self) -> None:
        """If ingest_finding encounters an error, projection is STALE, evidence persists."""
        from unittest.mock import MagicMock

        from app.models.agent_risk_posture import PostureState
        from app.models.watermark import BaselineWatermark
        from app.services.agent_lock_manager import AgentLockManager
        from app.services.risk_aggregator import RiskAggregator

        findings = FindingsService()
        aggregator = RiskAggregator()
        lock_mgr = AgentLockManager()

        # Initialize aggregate at baseline seq 0
        aggregator.reset_to_baseline(
            BaselineWatermark(agent_id=AGENT_ID, baseline_sequence=0)
        )

        # Fault injection inside aggregate apply_finding
        with aggregator._lock:
            aggregate = aggregator._projections[AGENT_ID]
        aggregate.apply_finding = MagicMock(
            side_effect=RuntimeError("Transient projection crash")
        )

        finding = make_finding("f-failure-test", agent_id=AGENT_ID)

        with lock_mgr.get_lock(AGENT_ID):
            recorded = findings.record_new_findings([finding])
            assert len(recorded) == 1
            assert recorded[0].evidence_sequence == 1

            for f in recorded:
                try:
                    aggregator.ingest_finding(f)
                except Exception:
                    aggregator.mark_stale(AGENT_ID)

        # Invariant 1: Evidence in FindingsService is NOT rolled back
        persisted = findings.list_findings(agent_id=AGENT_ID)
        assert len(persisted) == 1
        assert persisted[0].finding_id == "f-failure-test"

        # Invariant 2: Projection is STALE (fail-closed, cannot be consumed as HEALTHY)
        posture = aggregator.get_posture(AGENT_ID)
        assert posture.state == PostureState.STALE


class TestConcurrencyAndRaceSerialization:
    """Stress testing the serialization invariant between finding ingestion and reinstatement."""

    def test_reinstatement_vs_ingestion_race_preserves_serializable_invariants(
        self,
    ) -> None:
        """Concurrent reinstatement and finding ingestion always produce one of two valid serializations.

        Invariant asserted across repeated races:
        - Outcome is valid serialization: either reinstatement commits first or finding commits first.
        - Projection is either HEALTHY and semantically equivalent, or STALE.
        - NEVER: HEALTHY + missing post-baseline authoritative finding.
        """
        import threading

        from app.models.agent_risk_posture import PostureState
        from app.models.watermark import BaselineWatermark
        from app.services.agent_lock_manager import AgentLockManager
        from app.services.risk_aggregator import RiskAggregator

        for iteration in range(50):
            agent_id = f"race-agent-{iteration}"
            agents = create_test_agent_service()
            authority = ExecutionAuthority()
            findings = FindingsService()
            aggregator = RiskAggregator()
            lock_mgr = AgentLockManager()

            coordinator = EnforcementCoordinator(
                agents,
                authority,
                findings,
                risk_aggregator=aggregator,
                lock_manager=lock_mgr,
            )

            agents.register_agent(
                Agent(
                    agent_id=agent_id,
                    name="RaceAgent",
                    owner="security",
                    risk_tier=RiskTier.HIGH,
                    approved_tools=["file_read"],
                    status=AgentStatus.ACTIVE,
                )
            )

            # Pre-populate 5 historical findings: sequences 1..5
            for i in range(1, 6):
                findings.record_finding(make_finding(f"f-pre-{i}", agent_id=agent_id))

            contain(agents, authority, agent_id=agent_id)

            # Ingest pre-findings into aggregator at baseline 0 so projection exists
            aggregator.reset_to_baseline(
                BaselineWatermark(agent_id=agent_id, baseline_sequence=0)
            )
            for f in findings.list_findings(agent_id=agent_id):
                aggregator.ingest_finding(f)

            barrier = threading.Barrier(2)
            fresh_finding = make_finding(f"f-fresh-{iteration}", agent_id=agent_id)

            def run_reinstatement(c=coordinator, a_id=agent_id, b=barrier):
                b.wait()
                c.reinstate(a_id, actor="admin", reason="cleared")

            def run_ingestion(
                f_svc=findings,
                aggr=aggregator,
                lm=lock_mgr,
                a_id=agent_id,
                ff=fresh_finding,
                b=barrier,
            ):
                b.wait()
                with lm.get_lock(a_id):
                    recs = f_svc.record_new_findings([ff])
                    for f in recs:
                        aggr.ingest_finding(f)

            t1 = threading.Thread(target=run_reinstatement)
            t2 = threading.Thread(target=run_ingestion)

            t1.start()
            t2.start()
            t1.join()
            t2.join()

            # Verify authoritative evidence state
            all_persisted = findings.list_findings(agent_id=agent_id)
            assert len(all_persisted) == 6
            assert any(
                f.finding_id == f"f-fresh-{iteration}" and f.evidence_sequence == 6
                for f in all_persisted
            )

            baseline = agents.get_current_baseline(agent_id)
            posture = aggregator.get_posture(agent_id)

            # Assert core invariants:
            # 1. Posture must be HEALTHY (or STALE if error occurred)
            assert posture.state in (PostureState.HEALTHY, PostureState.STALE)

            if posture.state == PostureState.HEALTHY:
                # 2. Check which valid serialization occurred:
                if baseline.baseline_sequence == 5:
                    # Reinstatement serialized first: fresh finding (seq 6) is active post-baseline
                    assert posture.baseline_sequence == 5
                    assert posture.last_applied_sequence == 6
                    assert posture.finding_count == 1
                elif baseline.baseline_sequence == 6:
                    # Finding serialized first: fresh finding (seq 6) is absorbed into baseline epoch
                    assert posture.baseline_sequence == 6
                    assert posture.last_applied_sequence == 6
                    assert posture.finding_count == 0
                else:
                    pytest.fail(
                        f"Invalid baseline sequence: {baseline.baseline_sequence}"
                    )

                # 3. Posture MUST NEVER miss post-baseline authoritative finding:
                post_baseline_findings = [
                    f
                    for f in all_persisted
                    if f.evidence_sequence > baseline.baseline_sequence
                    and (
                        baseline.baseline_at is None
                        or (f.recorded_at or f.created_at) > baseline.baseline_at
                    )
                ]
                assert posture.finding_count == len(post_baseline_findings)
