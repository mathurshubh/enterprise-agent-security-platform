"""Unit tests for ExecutionEvidenceService (NEW-003)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_create_started_receipt():
    service = ExecutionEvidenceService()
    now = _utc_now()

    receipt = service.record_started(
        receipt_id="rcpt-1",
        grant_id="grant-1",
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="hash-123",
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
    service = ExecutionEvidenceService()
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-1",
        grant_id="grant-1",
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="hash-123",
        started_at=now,
    )

    with pytest.raises(ExecutionReceiptDuplicateError, match="already exists"):
        service.record_started(
            receipt_id="rcpt-1",
            grant_id="grant-2",
            session_id="session-1",
            agent_id="agent-1",
            tool_id="file_read",
            binding_hash="hash-123",
            started_at=now,
        )


def test_duplicate_grant_id_rejected_n3_9():
    """N3-9: At most one execution receipt may be associated with a given grant_id."""
    service = ExecutionEvidenceService()
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-1",
        grant_id="grant-1",
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="hash-123",
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
            tool_id="file_read",
            binding_hash="hash-123",
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
    service = ExecutionEvidenceService()
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-term",
        grant_id="grant-term",
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="hash-123",
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
    service = ExecutionEvidenceService()
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-inv",
        grant_id="grant-inv",
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="hash-123",
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
    service = ExecutionEvidenceService()
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-freeze",
        grant_id="grant-freeze",
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="hash-123",
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
    service = ExecutionEvidenceService()
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-recon",
        grant_id="grant-recon",
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="hash-123",
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
    service = ExecutionEvidenceService()
    now = _utc_now()

    service.record_started(
        receipt_id="rcpt-done",
        grant_id="grant-done",
        session_id="session-1",
        agent_id="agent-1",
        tool_id="file_read",
        binding_hash="hash-123",
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
    service = ExecutionEvidenceService()
    now = _utc_now()

    service.record_started(
        receipt_id="r1",
        grant_id="g1",
        session_id="s1",
        agent_id="agent-A",
        tool_id="file_read",
        binding_hash="h1",
        started_at=now,
    )
    service.record_started(
        receipt_id="r2",
        grant_id="g2",
        session_id="s2",
        agent_id="agent-A",
        tool_id="file_read",
        binding_hash="h2",
        started_at=now,
    )
    service.record_started(
        receipt_id="r3",
        grant_id="g3",
        session_id="s1",
        agent_id="agent-B",
        tool_id="file_read",
        binding_hash="h3",
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
    service = ExecutionEvidenceService()
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
            tool_id="file_read",
            binding_hash=f"hash-{idx}",
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
