"""Unit tests for ExecutionEvidenceService (NEW-003)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.execution_evidence_retention import (
    ExecutionEvidenceRetentionPolicy,
)
from app.models.execution_receipt import (
    ExecutionStatus,
    ReconciliationReason,
    compute_output_digest,
)
from app.services.execution_evidence_service import (
    ExecutionEvidenceService,
    ExecutionReceiptDuplicateError,
    ExecutionReceiptTransitionError,
)

# Generous bound: these tests exercise lifecycle semantics, not capacity.
_TEST_RETENTION = ExecutionEvidenceRetentionPolicy(max_terminal_receipts=1000)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_create_started_receipt():
    service = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)
    now = _utc_now()

    receipt = service.record_started(
        receipt_id="rcpt-1",
        grant_id="grant-1",
        session_id="session-1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="hash-123",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
        monotonic_start=100.5,
    )

    assert receipt.receipt_id == "rcpt-1"
    assert receipt.status == ExecutionStatus.STARTED
    assert receipt.agent_id == "agent-1"
    assert receipt.started_at == now
    assert service.get("rcpt-1") == receipt
    assert service.get_by_grant("grant-1") == receipt
    assert service.get_monotonic_start("rcpt-1") == 100.5
    assert len(service.list_open()) == 1


def test_duplicate_receipt_id_rejected():
    service = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-1",
        grant_id="grant-1",
        session_id="session-1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="hash-123",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
    )

    with pytest.raises(ExecutionReceiptDuplicateError, match="already exists"):
        service.record_started(
            receipt_id="rcpt-1",
            grant_id="grant-2",
            session_id="session-1",
            agent_id="agent-1",
            request_id="req-1",
            tool_id="file_read",
            binding_hash="hash-123",
            capability_profile_id="profile-file_read",
            capability_digest="d" * 64,
            declared_timeout_seconds=10.0,
            started_at=now,
        )


def test_duplicate_grant_id_rejected_n3_9():
    """N3-9: At most one execution receipt may be associated with a given grant_id."""
    service = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-1",
        grant_id="grant-1",
        session_id="session-1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="hash-123",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
    )

    with pytest.raises(
        ExecutionReceiptDuplicateError, match="already bound to receipt"
    ):
        service.record_started(
            receipt_id="rcpt-2",
            grant_id="grant-1",
            session_id="session-1",
            agent_id="agent-1",
            request_id="req-1",
            tool_id="file_read",
            binding_hash="hash-123",
            capability_profile_id="profile-file_read",
            capability_digest="d" * 64,
            declared_timeout_seconds=10.0,
            started_at=now,
        )


@pytest.mark.parametrize(
    "terminal_status",
    [
        ExecutionStatus.SUCCEEDED,
        ExecutionStatus.FAILED,
        ExecutionStatus.TIMEOUT,
        ExecutionStatus.INTERRUPTED,
    ],
)
def test_valid_terminal_transitions(terminal_status: ExecutionStatus):
    service = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-term",
        grant_id="grant-term",
        session_id="session-1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="hash-123",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
        monotonic_start=50.0,
    )

    completed_at = _utc_now()
    terminal = service.record_terminal(
        receipt_id="rcpt-term",
        status=terminal_status,
        completed_at=completed_at,
        duration_ms=42,
        error_type="SomeError"
        if terminal_status != ExecutionStatus.SUCCEEDED
        else None,
        error_code="SOME_CODE"
        if terminal_status != ExecutionStatus.SUCCEEDED
        else None,
        output_digest="digest-abc"
        if terminal_status == ExecutionStatus.SUCCEEDED
        else None,
    )

    assert terminal.status == terminal_status
    assert terminal.completed_at == completed_at
    assert terminal.duration_ms == 42
    assert service.get_monotonic_start("rcpt-term") is None
    assert len(service.list_open()) == 0


def test_invalid_terminal_status_rejected():
    """Executor cannot declare UNKNOWN via record_terminal."""
    service = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-inv",
        grant_id="grant-inv",
        session_id="session-1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="hash-123",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
    )

    with pytest.raises(
        ExecutionReceiptTransitionError, match="not an allowed executor terminal state"
    ):
        service.record_terminal(
            receipt_id="rcpt-inv",
            status=ExecutionStatus.UNKNOWN,
            completed_at=_utc_now(),
            duration_ms=10,
        )


def test_terminal_immutability_n3_4():
    """N3-4: A terminal execution state cannot be rewritten or transitioned."""
    service = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-freeze",
        grant_id="grant-freeze",
        session_id="session-1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="hash-123",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
    )

    service.record_terminal(
        receipt_id="rcpt-freeze",
        status=ExecutionStatus.SUCCEEDED,
        completed_at=_utc_now(),
        duration_ms=10,
    )

    with pytest.raises(
        ExecutionReceiptTransitionError,
        match="Cannot transition receipt .* from terminal status 'SUCCEEDED'",
    ):
        service.record_terminal(
            receipt_id="rcpt-freeze",
            status=ExecutionStatus.FAILED,
            completed_at=_utc_now(),
            duration_ms=20,
        )


def test_reconciliation_to_unknown_n3_5():
    """N3-5: Only reconciliation authority may transition an unresolved execution to UNKNOWN."""
    service = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-recon",
        grant_id="grant-recon",
        session_id="session-1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="hash-123",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
    )

    reconciled_at = _utc_now()
    reconciled = service.record_reconciled(
        receipt_id="rcpt-recon",
        reconciled_at=reconciled_at,
        reason=ReconciliationReason.EXECUTION_TIMEOUT,
    )

    assert reconciled.status == ExecutionStatus.UNKNOWN
    assert reconciled.reconciled_at == reconciled_at
    assert reconciled.reconciliation_reason == ReconciliationReason.EXECUTION_TIMEOUT
    assert len(service.list_open()) == 0


def test_non_started_reconciliation_rejected():
    service = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-done",
        grant_id="grant-done",
        session_id="session-1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="hash-123",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
    )

    service.record_terminal(
        receipt_id="rcpt-done",
        status=ExecutionStatus.SUCCEEDED,
        completed_at=_utc_now(),
        duration_ms=5,
    )

    with pytest.raises(
        ExecutionReceiptTransitionError,
        match="Cannot reconcile receipt .* from terminal status 'SUCCEEDED'",
    ):
        service.record_reconciled(
            receipt_id="rcpt-done",
            reconciled_at=_utc_now(),
            reason=ReconciliationReason.PROCESS_RESTART,
        )


def test_receipt_filtering():
    service = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)
    now = _utc_now()

    service.record_started(
        receipt_id="r1",
        grant_id="g1",
        session_id="s1",
        agent_id="agent-A",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="h1",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
    )
    service.record_started(
        receipt_id="r2",
        grant_id="g2",
        session_id="s2",
        agent_id="agent-A",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="h2",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
    )
    service.record_started(
        receipt_id="r3",
        grant_id="g3",
        session_id="s1",
        agent_id="agent-B",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="h3",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=now,
    )

    assert len(service.list_receipts()) == 3
    assert len(service.list_receipts(agent_id="agent-A")) == 2
    assert len(service.list_receipts(session_id="s1")) == 2
    assert len(service.list_receipts(session_id="s1", agent_id="agent-A")) == 1


def test_output_digest_strict_json():
    # Canonical JSON
    digest1 = compute_output_digest({"b": 2, "a": 1})
    digest2 = compute_output_digest({"a": 1, "b": 2})
    assert digest1 is not None
    assert digest1 == digest2

    # None returns None
    assert compute_output_digest(None) is None

    # Non-canonical / NaN returns None (strict JSON allow_nan=False)
    assert compute_output_digest(float("nan")) is None
    assert compute_output_digest(float("inf")) is None

    # Non-serializable object returns None
    class NonSerializable:
        pass

    assert compute_output_digest(NonSerializable()) is None


def test_thread_safe_access():
    service = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)
    now = _utc_now()
    count = 50

    def create_and_complete(idx: int):
        r_id = f"rcpt-concur-{idx}"
        g_id = f"grant-concur-{idx}"
        service.record_started(
            receipt_id=r_id,
            grant_id=g_id,
            session_id=f"sess-{idx % 3}",
            agent_id=f"agent-{idx % 2}",
            request_id="req-1",
            tool_id="file_read",
            binding_hash=f"hash-{idx}",
            capability_profile_id="profile-file_read",
            capability_digest="d" * 64,
            declared_timeout_seconds=10.0,
            started_at=now,
        )
        service.record_terminal(
            receipt_id=r_id,
            status=ExecutionStatus.SUCCEEDED,
            completed_at=_utc_now(),
            duration_ms=idx,
        )

    with ThreadPoolExecutor(max_workers=10) as executor:
        list(executor.map(create_and_complete, range(count)))

    assert len(service.list_receipts()) == count
    assert len(service.list_open()) == 0


def test_lifecycle_transitions_preserve_the_correlation_chain():
    """Terminalisation rebuilds the receipt, so every correlation field must be carried
    forward. Dropping one would leave an execution whose evidence cannot be joined back
    to the grant, request or capability that governed it — silently, and only on the
    terminal record rather than the STARTED one.
    """
    service = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)
    now = _utc_now()

    started = service.record_started(
        receipt_id="rcpt-chain",
        grant_id="grant-chain",
        session_id="session-9",
        agent_id="agent-9",
        request_id="req-9",
        tool_id="file_read",
        binding_hash="hash-9",
        capability_profile_id="profile-file_read",
        capability_digest="e" * 64,
        declared_timeout_seconds=42.0,
        started_at=now,
        monotonic_start=10.0,
    )

    chain = {
        "grant_id": "grant-chain",
        "session_id": "session-9",
        "agent_id": "agent-9",
        "request_id": "req-9",
        "capability_profile_id": "profile-file_read",
        "capability_digest": "e" * 64,
        "declared_timeout_seconds": 42.0,
    }
    for field, expected in chain.items():
        assert getattr(started, field) == expected, field

    terminal = service.record_terminal(
        receipt_id="rcpt-chain",
        status=ExecutionStatus.SUCCEEDED,
        completed_at=_utc_now(),
        duration_ms=5,
    )
    for field, expected in chain.items():
        assert getattr(terminal, field) == expected, f"terminal dropped {field}"


def test_reconciliation_preserves_the_correlation_chain():
    service = ExecutionEvidenceService(retention_policy=_TEST_RETENTION)

    service.record_started(
        receipt_id="rcpt-rec",
        grant_id="grant-rec",
        session_id="session-r",
        agent_id="agent-r",
        request_id="req-r",
        tool_id="file_read",
        binding_hash="hash-r",
        capability_profile_id="profile-file_read",
        capability_digest="f" * 64,
        declared_timeout_seconds=7.5,
        started_at=_utc_now(),
    )

    reconciled = service.record_reconciled(
        receipt_id="rcpt-rec",
        reconciled_at=_utc_now(),
        reason=ReconciliationReason.PROCESS_RESTART,
    )

    assert reconciled.status == ExecutionStatus.UNKNOWN
    assert reconciled.request_id == "req-r"
    assert reconciled.capability_profile_id == "profile-file_read"
    assert reconciled.capability_digest == "f" * 64
    assert reconciled.declared_timeout_seconds == 7.5


# ---------------------------------------------------------------------------
# v0.17.2 Step 6 — bounded terminal retention
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _bounded(max_terminal_receipts: int) -> ExecutionEvidenceService:
    return ExecutionEvidenceService(
        retention_policy=ExecutionEvidenceRetentionPolicy(
            max_terminal_receipts=max_terminal_receipts
        )
    )


def _started(service, name: str, *, offset: int = 0, monotonic: float | None = 1.0):
    return service.record_started(
        receipt_id=f"rcpt-{name}",
        grant_id=f"grant-{name}",
        session_id="session-1",
        agent_id="agent-1",
        request_id="req-1",
        tool_id="file_read",
        binding_hash="hash-1",
        capability_profile_id="profile-file_read",
        capability_digest="d" * 64,
        declared_timeout_seconds=10.0,
        started_at=_T0 + timedelta(seconds=offset),
        monotonic_start=monotonic,
    )


def _terminate(service, name: str):
    return service.record_terminal(
        receipt_id=f"rcpt-{name}",
        status=ExecutionStatus.SUCCEEDED,
        completed_at=_T0 + timedelta(seconds=100),
        duration_ms=1,
    )


@pytest.mark.parametrize("invalid", [0, -1, -1000])
def test_a_retention_bound_below_one_is_rejected(invalid: int) -> None:
    """Bounded means bounded to something. Zero would retain no evidence at all."""
    with pytest.raises(ValidationError):
        ExecutionEvidenceRetentionPolicy(max_terminal_receipts=invalid)


def test_the_bound_has_no_domain_default() -> None:
    """Capacity is a deployment decision. A platform that knows nothing about a
    deployment's execution volume must not invent one."""
    with pytest.raises(ValidationError):
        ExecutionEvidenceRetentionPolicy()


def test_terminal_receipts_are_evicted_oldest_first() -> None:
    service = _bounded(2)
    for i, name in enumerate(("a", "b", "c")):
        _started(service, name, offset=i)
        _terminate(service, name)

    retained = {r.receipt_id for r in service.list_receipts()}
    assert retained == {"rcpt-b", "rcpt-c"}, "the oldest terminal receipt is evicted"


def test_exactly_the_configured_capacity_is_retained_without_eviction() -> None:
    """No unnecessary eviction at the boundary."""
    service = _bounded(3)
    for i, name in enumerate(("a", "b", "c")):
        _started(service, name, offset=i)
        _terminate(service, name)

    assert len(service.list_receipts()) == 3
    assert service.get("rcpt-a") is not None


def test_open_receipts_are_never_evicted_by_retention() -> None:
    """An open receipt is the reconciler's only input, so evicting one would convert a
    reconcilable unknown into a silently lost execution."""
    service = _bounded(1)
    for i, name in enumerate(("a", "b", "c", "d")):
        _started(service, name, offset=i)

    assert len(service.list_open()) == 4, "no open receipt may be evicted"
    assert len(service.list_receipts()) == 4


def test_only_terminal_receipts_participate_in_eviction() -> None:
    """Mixed lifecycle: the bound counts terminal receipts, and open ones neither
    count towards it nor are removed by it."""
    service = _bounded(1)
    _started(service, "open-1", offset=0)
    _started(service, "open-2", offset=1)
    for i, name in enumerate(("t1", "t2", "t3"), start=2):
        _started(service, name, offset=i)
        _terminate(service, name)

    open_ids = {r.receipt_id for r in service.list_open()}
    assert open_ids == {"rcpt-open-1", "rcpt-open-2"}

    terminal_ids = {
        r.receipt_id
        for r in service.list_receipts()
        if r.status != ExecutionStatus.STARTED
    }
    assert terminal_ids == {"rcpt-t3"}, "only the newest terminal receipt is retained"


def test_a_reconciled_unknown_receipt_is_evictable() -> None:
    """UNKNOWN is terminal, so it is subject to the same bound."""
    service = _bounded(1)
    _started(service, "unknown-old", offset=0)
    service.record_reconciled(
        receipt_id="rcpt-unknown-old",
        reconciled_at=_T0 + timedelta(seconds=50),
        reason=ReconciliationReason.PROCESS_RESTART,
    )
    _started(service, "newer", offset=1)
    _terminate(service, "newer")

    retained = {r.receipt_id for r in service.list_receipts()}
    assert retained == {"rcpt-newer"}


def test_eviction_prunes_every_structure_keyed_by_the_receipt() -> None:
    """The bound applies to the complete in-memory evidence state.

    Bounding the receipt dictionary alone would leave the grant index growing without
    limit, so the store would remain unbounded while appearing bounded.

    Note on where each structure is actually released. ``_grant_to_receipt`` survives
    terminalization and is pruned only here, so eviction is what bounds it.
    ``_monotonic_starts`` is already released when a receipt terminalizes, so the
    eviction-loop pop is defensive rather than load-bearing — its entries are bounded by
    terminalization, and an entry persisting belongs to an open receipt, which retention
    deliberately does not evict. Both are asserted so the total state is checked
    regardless of which step released it.
    """
    service = _bounded(1)
    _started(service, "evicted", offset=0, monotonic=5.0)
    _terminate(service, "evicted")
    _started(service, "kept", offset=1, monotonic=6.0)
    _terminate(service, "kept")

    assert service.get("rcpt-evicted") is None
    assert service.get_by_grant("grant-evicted") is None, "grant index not pruned"
    assert service.get_monotonic_start("rcpt-evicted") is None, "timing state not pruned"

    # Internal state asserted directly: the public surface cannot distinguish a pruned
    # index from one that still holds a dangling entry.
    assert "grant-evicted" not in service._grant_to_receipt
    assert "rcpt-evicted" not in service._monotonic_starts
    assert "rcpt-evicted" not in service._receipts


def test_retention_does_not_run_on_record_started() -> None:
    """The bound is on terminal evidence. A backlog of open receipts must not be
    absorbed by retention, however many terminal receipts exist."""
    service = _bounded(1)
    _started(service, "terminal", offset=0)
    _terminate(service, "terminal")

    for i in range(5):
        _started(service, f"open-{i}", offset=10 + i)

    assert len(service.list_open()) == 5
    assert service.get("rcpt-terminal") is not None


# ---------------------------------------------------------------------------
# v0.17.2 Step 7 — lifecycle observability
# ---------------------------------------------------------------------------


def test_counters_start_at_zero() -> None:
    service = _bounded(10)

    assert service.open_receipt_count == 0
    assert service.terminal_receipt_count == 0
    assert service.evidence_failure_count == 0
    assert service.reconciled_unknown_count == 0


def test_an_open_receipt_counts_as_open_and_not_terminal() -> None:
    service = _bounded(10)
    _started(service, "a")

    assert service.open_receipt_count == 1
    assert service.terminal_receipt_count == 0


def test_terminalisation_moves_a_receipt_from_open_to_terminal() -> None:
    service = _bounded(10)
    _started(service, "a")
    _terminate(service, "a")

    assert service.open_receipt_count == 0
    assert service.terminal_receipt_count == 1


def test_a_reconciled_unknown_receipt_counts_as_terminal() -> None:
    service = _bounded(10)
    _started(service, "a")
    service.record_reconciled(
        receipt_id="rcpt-a",
        reconciled_at=_T0 + timedelta(seconds=5),
        reason=ReconciliationReason.PROCESS_RESTART,
    )

    assert service.open_receipt_count == 0
    assert service.terminal_receipt_count == 1


def test_reconciliation_to_unknown_is_counted_exactly_once() -> None:
    """Counted at the transition, not inferred from the receipt population: a receipt
    can be evicted while remaining a fact about what reconciliation did."""
    service = _bounded(1)
    _started(service, "a")
    service.record_reconciled(
        receipt_id="rcpt-a",
        reconciled_at=_T0 + timedelta(seconds=5),
        reason=ReconciliationReason.EXECUTION_TIMEOUT,
    )
    assert service.reconciled_unknown_count == 1

    # A second reconciliation of the same receipt is refused, so nothing double-counts.
    with pytest.raises(ExecutionReceiptTransitionError):
        service.record_reconciled(
            receipt_id="rcpt-a",
            reconciled_at=_T0 + timedelta(seconds=6),
            reason=ReconciliationReason.EXECUTION_TIMEOUT,
        )
    assert service.reconciled_unknown_count == 1

    # And it survives the receipt being evicted by retention.
    _started(service, "b", offset=10)
    _terminate(service, "b")
    assert service.get("rcpt-a") is None
    assert service.reconciled_unknown_count == 1


def test_an_evidence_persistence_failure_is_counted() -> None:
    """Persistence failures, never execution failures."""
    service = _bounded(10)
    _started(service, "a")

    with pytest.raises(ExecutionReceiptDuplicateError):
        _started(service, "a")

    assert service.evidence_failure_count == 1


def test_the_self_resolution_race_is_not_counted_as_an_evidence_failure() -> None:
    """A transition rejected because the receipt already terminalised is ordinary
    concurrency (Step 4). Counting it would make a race look like an integrity fault."""
    service = _bounded(10)
    _started(service, "a")
    _terminate(service, "a")

    with pytest.raises(ExecutionReceiptTransitionError):
        _terminate(service, "a")

    assert service.evidence_failure_count == 0


def test_counters_stay_consistent_after_eviction() -> None:
    """Derived from authoritative state, so eviction cannot leave them disagreeing
    with the receipts themselves."""
    service = _bounded(2)
    _started(service, "open-1", offset=0)
    for i, name in enumerate(("a", "b", "c"), start=1):
        _started(service, name, offset=i)
        _terminate(service, name)

    assert service.terminal_receipt_count == 2, "bounded by retention"
    assert service.open_receipt_count == 1, "the open receipt is untouched"
    assert len(service.list_receipts()) == 3
