"""Unit tests for ExecutionReconciler (NEW-003)."""

from datetime import datetime, timezone

from app.models.execution_receipt import (
    ExecutionStatus,
    ReconciliationReason,
)
from app.services.execution_evidence_service import ExecutionEvidenceService
from app.services.execution_reconciler import ExecutionReconciler


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_reconcile_on_startup():
    store = ExecutionEvidenceService()
    now = _utc_now()

    store.record_started(
        receipt_id="r-startup-1",
        grant_id="g-startup-1",
        session_id="s1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="h1",
        started_at=now,
    )
    store.record_started(
        receipt_id="r-startup-2",
        grant_id="g-startup-2",
        session_id="s1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="h2",
        started_at=now,
    )

    reconciler = ExecutionReconciler(evidence_store=store)
    startup_now = _utc_now()
    reconciled = reconciler.reconcile_on_startup(startup_now)

    assert len(reconciled) == 2
    for r in reconciled:
        assert r.status == ExecutionStatus.UNKNOWN
        assert r.reconciliation_reason == ReconciliationReason.PROCESS_RESTART
        assert r.reconciled_at == startup_now

    assert len(store.list_open()) == 0


def test_reconcile_unresolved_evaluates_per_receipt_monotonic_time():
    """N3-11: Reconciler evaluates each receipt independently using its monotonic start."""
    store = ExecutionEvidenceService()
    now = _utc_now()

    # Receipt 1: started at monotonic 10.0 (old)
    store.record_started(
        receipt_id="r-old",
        grant_id="g-old",
        session_id="s1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="h1",
        started_at=now,
        monotonic_start=10.0,
    )

    # Receipt 2: started at monotonic 45.0 (recent)
    store.record_started(
        receipt_id="r-recent",
        grant_id="g-recent",
        session_id="s1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="h2",
        started_at=now,
        monotonic_start=45.0,
    )

    # SLA = 30s, grace = 10s -> deadline threshold = 40s
    reconciler = ExecutionReconciler(
        evidence_store=store,
        default_execution_sla_seconds=30.0,
        recovery_grace_seconds=10.0,
    )

    # Current monotonic time: 55.0
    # r-old elapsed = 55.0 - 10.0 = 45.0 >= 40.0 -> RECONCILE
    # r-recent elapsed = 55.0 - 45.0 = 10.0 < 40.0 -> REMAINS STARTED
    reconcile_time = _utc_now()
    reconciled = reconciler.reconcile_unresolved(
        now_utc=reconcile_time,
        monotonic_now=55.0,
    )

    assert len(reconciled) == 1
    assert reconciled[0].receipt_id == "r-old"
    assert reconciled[0].status == ExecutionStatus.UNKNOWN
    assert reconciled[0].reconciliation_reason == ReconciliationReason.EXECUTION_TIMEOUT

    # r-recent remains open
    open_receipts = store.list_open()
    assert len(open_receipts) == 1
    assert open_receipts[0].receipt_id == "r-recent"


def test_reconcile_unresolved_missing_monotonic_evidence():
    """Missing monotonic start evidence reconciles as EVIDENCE_UNAVAILABLE."""
    store = ExecutionEvidenceService()
    now = _utc_now()

    store.record_started(
        receipt_id="r-no-mono",
        grant_id="g-no-mono",
        session_id="s1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="h1",
        started_at=now,
        monotonic_start=None,
    )

    reconciler = ExecutionReconciler(evidence_store=store)
    reconciled = reconciler.reconcile_unresolved(
        now_utc=_utc_now(), monotonic_now=100.0
    )

    assert len(reconciled) == 1
    assert reconciled[0].receipt_id == "r-no-mono"
    assert reconciled[0].status == ExecutionStatus.UNKNOWN
    assert (
        reconciled[0].reconciliation_reason == ReconciliationReason.EVIDENCE_UNAVAILABLE
    )
