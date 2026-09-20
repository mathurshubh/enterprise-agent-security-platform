"""ExecutionReconciler — Authoritative reconciliation layer for execution evidence (NEW-003).

Invariants:
- N3-5 (Reconciliation Authority): Only the reconciliation layer may transition an unresolved execution to UNKNOWN.
- N3-11 (Per-Receipt Elapsed Time): Evaluates monotonic duration per execution receipt against execution SLA and recovery grace.
- M4-7 (Epistemic Preservation): Missing execution evidence must not be converted to SUCCEEDED or FAILED; it is preserved as UNKNOWN.
"""

import time
from collections.abc import Callable
from datetime import datetime

from app.models.execution_receipt import (
    ExecutionReceipt,
    ReconciliationReason,
)
from app.runtime.contracts import ExecutionEvidenceStoreProtocol

DEFAULT_EXECUTION_SLA_SECONDS = 30.0
DEFAULT_RECOVERY_GRACE_SECONDS = 10.0


class ExecutionReconciler:
    """Authoritative reconciliation layer for establishing UNKNOWN execution status."""

    def __init__(
        self,
        evidence_store: ExecutionEvidenceStoreProtocol,
        default_execution_sla_seconds: float = DEFAULT_EXECUTION_SLA_SECONDS,
        recovery_grace_seconds: float = DEFAULT_RECOVERY_GRACE_SECONDS,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = evidence_store
        self._default_sla = default_execution_sla_seconds
        self._grace = recovery_grace_seconds
        self._clock = monotonic_clock

    def reconcile_on_startup(self, now_utc: datetime) -> tuple[ExecutionReceipt, ...]:
        """Crash consistency: reconcile previously STARTED receipts discovered at startup.

        For the current in-memory evidence store, an ordinary process restart creates
        an empty store. When a durable evidence store is introduced, this method
        reconciles orphaned receipts that were in-flight when the previous process died.
        """
        open_receipts = self._store.list_open()
        reconciled = []
        for receipt in open_receipts:
            rec = self._store.record_reconciled(
                receipt_id=receipt.receipt_id,
                reconciled_at=now_utc,
                reason=ReconciliationReason.PROCESS_RESTART,
            )
            reconciled.append(rec)
        return tuple(reconciled)

    def reconcile_unresolved(
        self,
        *,
        now_utc: datetime,
        monotonic_now: float | None = None,
        sla_seconds: float | None = None,
    ) -> tuple[ExecutionReceipt, ...]:
        """Reconcile in-flight receipts whose execution has exceeded the SLA and grace window.

        Evaluates each receipt independently using its recorded monotonic start time.
        """
        current_monotonic = (
            monotonic_now if monotonic_now is not None else self._clock()
        )
        effective_sla = sla_seconds if sla_seconds is not None else self._default_sla
        deadline_threshold = effective_sla + self._grace

        open_receipts = self._store.list_open()
        reconciled = []

        for receipt in open_receipts:
            # Retrieve per-receipt monotonic start
            start_mono = getattr(self._store, "get_monotonic_start", lambda _: None)(
                receipt.receipt_id
            )

            if start_mono is None:
                # Execution start evidence lacks monotonic timing; outcome is unrecoverable
                rec = self._store.record_reconciled(
                    receipt_id=receipt.receipt_id,
                    reconciled_at=now_utc,
                    reason=ReconciliationReason.EVIDENCE_UNAVAILABLE,
                )
                reconciled.append(rec)
                continue

            elapsed = current_monotonic - start_mono
            if elapsed >= deadline_threshold:
                rec = self._store.record_reconciled(
                    receipt_id=receipt.receipt_id,
                    reconciled_at=now_utc,
                    reason=ReconciliationReason.EXECUTION_TIMEOUT,
                )
                reconciled.append(rec)

        return tuple(reconciled)
