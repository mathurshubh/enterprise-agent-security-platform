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
        request_id="req-1",
        tool_id="file_read",
        binding_hash="h1",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
    )
    store.record_started(
        receipt_id="r-startup-2",
        grant_id="g-startup-2",
        session_id="s1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="h2",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
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
        request_id="req-1",
        tool_id="file_read",
        binding_hash="h1",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
        monotonic_start=10.0,
    )

    # Receipt 2: started at monotonic 45.0 (recent)
    store.record_started(
        receipt_id="r-recent",
        grant_id="g-recent",
        session_id="s1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="h2",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
        monotonic_start=45.0,
    )

    # Each receipt declares a 10s execution budget; grace = 10s, so a receipt is
    # reconcilable at start + 10 + 10 = start + 20.
    reconciler = ExecutionReconciler(
        evidence_store=store,
        recovery_grace_seconds=10.0,
    )

    # Current monotonic time: 55.0
    # r-old    deadline = 10.0 + 10 + 10 = 30.0 <= 55.0 -> RECONCILE
    # r-recent deadline = 45.0 + 10 + 10 = 65.0 >  55.0 -> REMAINS STARTED
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
        request_id="req-1",
        tool_id="file_read",
        binding_hash="h1",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
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


def _start(store, receipt_id: str, *, declared_timeout_seconds: float,
           monotonic_start: float, grant_id: str | None = None):
    return store.record_started(
        receipt_id=receipt_id,
        grant_id=grant_id or f"g-{receipt_id}",
        session_id="s1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="h1",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=declared_timeout_seconds,
        started_at=_utc_now(),
        monotonic_start=monotonic_start,
    )


def test_a_long_running_execution_inside_its_declared_budget_is_not_reconciled():
    """The reconciler must not manufacture an execution outcome that did not happen.

    A single global SLA was authoritative here, and it could be shorter than the limit
    the capability actually declared: 30s SLA + 10s grace against a
    ``wall_clock_timeout_seconds`` of up to 600s. An execution legitimately running for
    120s was therefore declared UNKNOWN at 40s and attributed EXECUTION_TIMEOUT — the
    platform asserting a timeout that had not occurred, and permanently losing the real
    outcome, because N3-4 then refuses the genuine terminal transition.

    This is the acceptance property for that fix: at 40s elapsed, a receipt declaring a
    120s budget is still open.
    """
    store = ExecutionEvidenceService()
    _start(store, "r-long", declared_timeout_seconds=120.0, monotonic_start=0.0)

    reconciler = ExecutionReconciler(evidence_store=store, recovery_grace_seconds=10.0)

    reconciled = reconciler.reconcile_unresolved(
        now_utc=_utc_now(),
        monotonic_now=40.0,  # past the retired 30 + 10 global threshold
    )

    assert reconciled == (), "an execution inside its declared budget is not unresolved"
    open_receipts = store.list_open()
    assert len(open_receipts) == 1
    assert open_receipts[0].receipt_id == "r-long"
    assert open_receipts[0].status == ExecutionStatus.STARTED


def test_reconciliation_becomes_eligible_after_the_declared_budget_plus_grace():
    """Two clocks: the execution deadline is the declared budget; the reconciliation
    deadline adds the allowance for observing an outcome after that limit passed."""
    store = ExecutionEvidenceService()
    _start(store, "r-long", declared_timeout_seconds=120.0, monotonic_start=0.0)
    reconciler = ExecutionReconciler(evidence_store=store, recovery_grace_seconds=10.0)

    # Past the execution deadline (120) but inside the grace window: still open.
    assert reconciler.reconcile_unresolved(now_utc=_utc_now(), monotonic_now=125.0) == ()
    assert len(store.list_open()) == 1

    # At execution deadline + grace exactly: eligible.
    reconciled = reconciler.reconcile_unresolved(now_utc=_utc_now(), monotonic_now=130.0)

    assert len(reconciled) == 1
    assert reconciled[0].receipt_id == "r-long"
    assert reconciled[0].status == ExecutionStatus.UNKNOWN
    assert reconciled[0].reconciliation_reason == ReconciliationReason.EXECUTION_TIMEOUT
    assert store.list_open() == ()


def test_each_receipt_is_evaluated_against_its_own_declared_budget():
    """Per-receipt, not per-batch: one deadline cannot be applied to every execution,
    because different capabilities declare different limits."""
    store = ExecutionEvidenceService()
    _start(store, "r-short", declared_timeout_seconds=5.0, monotonic_start=0.0)
    _start(store, "r-long", declared_timeout_seconds=600.0, monotonic_start=0.0)
    reconciler = ExecutionReconciler(evidence_store=store, recovery_grace_seconds=10.0)

    reconciled = reconciler.reconcile_unresolved(now_utc=_utc_now(), monotonic_now=20.0)

    assert [r.receipt_id for r in reconciled] == ["r-short"]
    assert [r.receipt_id for r in store.list_open()] == ["r-long"]


class _StoreWithoutMonotonicAccessor:
    """Conforms to every part of the evidence store contract except the timing accessor.

    This is the shape that made reconciliation degrade silently: the accessor was read
    through ``getattr(..., lambda _: None)``, so its absence was indistinguishable from
    "this receipt has no recorded timing", and every open receipt was reconciled to
    UNKNOWN. Reconciliation reported that all executions were unrecoverable when the
    truth was that reconciliation could not run.
    """

    def __init__(self, open_receipt) -> None:
        self._open = (open_receipt,)
        self.reconciled: list[str] = []

    def record_started(self, **kwargs):  # pragma: no cover - not exercised
        raise NotImplementedError

    def record_terminal(self, **kwargs):  # pragma: no cover - not exercised
        raise NotImplementedError

    def record_reconciled(self, *, receipt_id, reconciled_at, reason):
        self.reconciled.append(receipt_id)
        return self._open[0]

    def get(self, receipt_id):  # pragma: no cover - not exercised
        return None

    def get_by_grant(self, grant_id):  # pragma: no cover - not exercised
        return None

    def list_open(self):
        return self._open

    def list_receipts(self, session_id=None, agent_id=None):  # pragma: no cover
        return ()


def _open_receipt():
    store = ExecutionEvidenceService()
    return _start(store, "r-probe", declared_timeout_seconds=10.0, monotonic_start=0.0)


def test_a_store_violating_the_evidence_contract_is_refused_at_wiring():
    """A missing contract is a wiring fault, not an execution outcome."""
    import pytest

    store = _StoreWithoutMonotonicAccessor(_open_receipt())

    with pytest.raises(TypeError, match="ExecutionEvidenceStoreProtocol"):
        ExecutionReconciler(evidence_store=store)

    assert store.reconciled == [], "a refused wiring may not reconcile anything"


def test_reconciliation_does_not_silently_degrade_if_the_contract_is_bypassed():
    """Defense in depth, and the discriminating test for the loop itself.

    The construction check above makes the missing accessor unreachable through normal
    wiring, so it alone cannot distinguish a direct protocol call from the old
    ``getattr`` fallback. This asserts the loop's own behaviour: presented with a store
    that cannot answer, reconciliation fails loudly rather than declaring the execution
    unrecoverable.
    """
    import pytest

    reconciler = ExecutionReconciler(evidence_store=ExecutionEvidenceService())
    bad_store = _StoreWithoutMonotonicAccessor(_open_receipt())
    reconciler._store = bad_store

    with pytest.raises(AttributeError):
        reconciler.reconcile_unresolved(now_utc=_utc_now(), monotonic_now=100.0)

    assert bad_store.reconciled == [], (
        "the receipt must not be reconciled to UNKNOWN because the store could not "
        "report its timing"
    )


def test_missing_timing_evidence_remains_reconcilable():
    """The semantic distinction the contract preserves: a conforming store returning
    None means the timing is genuinely missing, which is still a reconcilable
    condition and keeps its existing EVIDENCE_UNAVAILABLE outcome."""
    store = ExecutionEvidenceService()
    store.record_started(
        receipt_id="r-no-timing",
        grant_id="g-no-timing",
        session_id="s1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="h1",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=_utc_now(),
        # monotonic_start deliberately omitted
    )
    assert store.get_monotonic_start("r-no-timing") is None

    reconciler = ExecutionReconciler(evidence_store=store)
    reconciled = reconciler.reconcile_unresolved(now_utc=_utc_now(), monotonic_now=1.0)

    assert len(reconciled) == 1
    assert reconciled[0].status == ExecutionStatus.UNKNOWN
    assert (
        reconciled[0].reconciliation_reason == ReconciliationReason.EVIDENCE_UNAVAILABLE
    )


def test_the_production_store_satisfies_the_evidence_contract() -> None:
    """The contract must describe the implementation, not an aspiration."""
    from app.runtime.contracts import ExecutionEvidenceStoreProtocol

    assert isinstance(ExecutionEvidenceService(), ExecutionEvidenceStoreProtocol)
    assert hasattr(ExecutionEvidenceStoreProtocol, "get_monotonic_start")
