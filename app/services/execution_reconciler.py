"""ExecutionReconciler — Authoritative reconciliation layer for execution evidence (ADR-032 §12).

Invariants:
- N3-5 (Reconciliation Authority): Only the reconciliation layer may transition an unresolved execution to UNKNOWN.
- N3-11 (Per-Receipt Elapsed Time): Evaluates monotonic duration per execution receipt
  against the execution budget the governing capability declared, plus recovery grace.

Two distinct clocks
-------------------
    execution_deadline      = started + receipt.declared_timeout_seconds
    reconciliation_deadline = execution_deadline + recovery_grace

The execution timeout answers *how long may this execution legitimately run*; the
recovery grace answers *how long after that limit before the outcome is unrecoverable*.
They are never collapsed into one generic SLA.

A single global SLA was authoritative here previously, and it could be shorter than a
capability's declared ``wall_clock_timeout_seconds`` (30s + 10s grace against a limit of
up to 600s). The reconciler would then declare a still-running execution UNKNOWN and
attribute EXECUTION_TIMEOUT to it — a security platform manufacturing an execution
outcome that had not happened. The deadline is therefore derived per receipt, from the
limit that actually governed that execution.
- M4-7 (Epistemic Preservation): Missing execution evidence must not be converted to SUCCEEDED or FAILED; it is preserved as UNKNOWN.
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime

from app.models.execution_receipt import (
    ExecutionReceipt,
    ReconciliationReason,
)
from app.runtime.contracts import ExecutionEvidenceStoreProtocol
from app.services.execution_evidence_service import ExecutionReceiptTransitionError

logger = logging.getLogger(__name__)

DEFAULT_RECOVERY_GRACE_SECONDS = 10.0


class ExecutionReconciler:
    """Authoritative reconciliation layer for establishing UNKNOWN execution status."""

    def __init__(
        self,
        evidence_store: ExecutionEvidenceStoreProtocol,
        recovery_grace_seconds: float = DEFAULT_RECOVERY_GRACE_SECONDS,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(evidence_store, ExecutionEvidenceStoreProtocol):
            # Refused at wiring time. Reconciliation read the timing accessor through
            # getattr with a None default, so a store not providing it silently
            # reconciled every open receipt to UNKNOWN — reconciliation degrading to
            # "declare everything unrecoverable" rather than reporting that it could
            # not run. A missing contract is a wiring fault, not an execution outcome.
            raise TypeError(
                "evidence_store does not satisfy ExecutionEvidenceStoreProtocol: "
                "reconciliation requires list_open, get_monotonic_start and "
                "record_reconciled"
            )

        # No global execution SLA: the execution budget belongs to the receipt, because
        # it belongs to the capability that governed that execution. A configurable
        # global value here would be a parameter that appears to control the deadline
        # while being able to contradict the limit the platform actually enforced.
        self._store = evidence_store
        self._grace = recovery_grace_seconds
        self._clock = monotonic_clock

    def _reconcile_one(
        self,
        receipt: ExecutionReceipt,
        now_utc: datetime,
        reason: ReconciliationReason,
    ) -> ExecutionReceipt | None:
        """Reconcile one receipt, tolerating the expected race and isolating failures.

        Reconciliation reads a snapshot from ``list_open()``, so a receipt may be
        terminalized independently between the snapshot and this transition. That is
        ordinary concurrency and the better outcome: the execution reported its own
        result. The receipt is treated as resolved and is not returned as reconciled,
        because nothing here reconciled it and it did not become UNKNOWN.

        A genuinely unexpected failure is isolated to this receipt and observed. One
        receipt must not compromise reconciliation of unrelated receipts, or a single
        bad record becomes a batch-wide availability failure.

        Returns:
            The reconciled receipt, or None if it self-resolved or could not be
            reconciled.
        """
        try:
            return self._store.record_reconciled(
                receipt_id=receipt.receipt_id,
                reconciled_at=now_utc,
                reason=reason,
            )
        except ExecutionReceiptTransitionError:
            # Expected: the receipt reached a terminal state on its own. Not a failure,
            # and deliberately not counted as a reconciliation.
            return None
        except Exception as exc:
            # Only the exception type is recorded, never its message (N3-7).
            logger.warning(
                "Reconciliation failed for receipt %s (%s); continuing batch",
                receipt.receipt_id,
                type(exc).__name__,
            )
            return None

    def reconcile_on_startup(self, now_utc: datetime) -> tuple[ExecutionReceipt, ...]:
        """Crash consistency: reconcile previously STARTED receipts discovered at startup.

        For the current in-memory evidence store, an ordinary process restart creates
        an empty store. When a durable evidence store is introduced, this method
        reconciles orphaned receipts that were in-flight when the previous process died.
        """
        open_receipts = self._store.list_open()
        reconciled = []
        for receipt in open_receipts:
            rec = self._reconcile_one(
                receipt, now_utc, ReconciliationReason.PROCESS_RESTART
            )
            if rec is not None:
                reconciled.append(rec)
        return tuple(reconciled)

    def reconcile_unresolved(
        self,
        *,
        now_utc: datetime,
        monotonic_now: float | None = None,
    ) -> tuple[ExecutionReceipt, ...]:
        """Reconcile in-flight receipts past their declared execution budget plus grace.

        Evaluates each receipt independently, using its recorded monotonic start and the
        execution budget declared by the capability that governed it. An execution still
        within its own declared limit is never reconciled, however long that limit is.
        """
        current_monotonic = (
            monotonic_now if monotonic_now is not None else self._clock()
        )

        open_receipts = self._store.list_open()
        reconciled = []

        for receipt in open_receipts:
            # Direct protocol call: None means the timing evidence is genuinely
            # missing for this receipt, which is reconcilable. It no longer doubles as
            # "the store does not implement this", which the construction check refuses.
            start_mono = self._store.get_monotonic_start(receipt.receipt_id)

            if start_mono is None:
                # Execution start evidence lacks monotonic timing; outcome is unrecoverable
                rec = self._reconcile_one(
                    receipt, now_utc, ReconciliationReason.EVIDENCE_UNAVAILABLE
                )
                if rec is not None:
                    reconciled.append(rec)
                continue

            # Two clocks, kept separate: the execution deadline is the limit the
            # capability declared for this execution; the reconciliation deadline adds
            # the allowance for observing an outcome after that limit has passed.
            execution_deadline = start_mono + receipt.declared_timeout_seconds
            reconciliation_deadline = execution_deadline + self._grace

            if current_monotonic >= reconciliation_deadline:
                rec = self._reconcile_one(
                    receipt, now_utc, ReconciliationReason.EXECUTION_TIMEOUT
                )
                if rec is not None:
                    reconciled.append(rec)

        return tuple(reconciled)
