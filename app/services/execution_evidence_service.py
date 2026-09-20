"""ExecutionEvidenceService — Authoritative in-memory store for execution receipts (NEW-003).

Invariants:
- N3-1 (Receipt Provenance): Identity and binding derived exclusively from verified grant/context.
- N3-4 (Terminal Monotonicity): Terminal execution states are immutable and cannot be transitioned.
- N3-5 (Reconciliation Authority): Transition to UNKNOWN is reserved for reconciliation authority.
- N3-7 (Diagnostic Safety): Raw exception messages excluded.
- N3-9 (Grant Receipt Uniqueness): Exactly one receipt may be created per grant_id.
- N3-10 (UTC Evidence Time): Enforces timezone-aware UTC timestamps.
- N3-11 (Per-Receipt Elapsed Time): Tracks monotonic start per receipt for duration validation.
"""

from datetime import datetime
from threading import RLock

from app.models.execution_receipt import (
    ExecutionReceipt,
    ExecutionStatus,
    ReconciliationReason,
)
from app.runtime.contracts import ExecutionEvidenceStoreProtocol

ALLOWED_TERMINAL_STATUSES = frozenset(
    {
        ExecutionStatus.SUCCEEDED,
        ExecutionStatus.FAILED,
        ExecutionStatus.TIMEOUT,
        ExecutionStatus.INTERRUPTED,
    }
)


class ExecutionReceiptNotFoundError(KeyError):
    """Raised when an execution receipt cannot be found."""


class ExecutionReceiptDuplicateError(ValueError):
    """Raised when attempting to register a duplicate receipt_id or grant_id."""


class ExecutionReceiptTransitionError(ValueError):
    """Raised when an invalid lifecycle state transition is attempted on an execution receipt."""


class ExecutionEvidenceService(ExecutionEvidenceStoreProtocol):
    """Thread-safe authoritative store for tool execution receipts."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._receipts: dict[str, ExecutionReceipt] = {}
        self._grant_to_receipt: dict[str, str] = {}
        self._monotonic_starts: dict[str, float] = {}

    def record_started(
        self,
        *,
        receipt_id: str,
        grant_id: str,
        session_id: str,
        agent_id: str,
        tool_id: str,
        binding_hash: str,
        started_at: datetime,
        monotonic_start: float | None = None,
    ) -> ExecutionReceipt:
        """Record the initial STARTED receipt at the tool execution boundary."""
        with self._lock:
            if receipt_id in self._receipts:
                raise ExecutionReceiptDuplicateError(
                    f"Execution receipt '{receipt_id}' already exists"
                )

            if grant_id in self._grant_to_receipt:
                raise ExecutionReceiptDuplicateError(
                    f"Grant '{grant_id}' is already bound to receipt '{self._grant_to_receipt[grant_id]}'"
                )

            receipt = ExecutionReceipt(
                receipt_id=receipt_id,
                grant_id=grant_id,
                session_id=session_id,
                agent_id=agent_id,
                tool_id=tool_id,
                binding_hash=binding_hash,
                status=ExecutionStatus.STARTED,
                started_at=started_at,
            )

            self._receipts[receipt_id] = receipt
            self._grant_to_receipt[grant_id] = receipt_id
            if monotonic_start is not None:
                self._monotonic_starts[receipt_id] = monotonic_start

            return receipt

    def record_terminal(
        self,
        *,
        receipt_id: str,
        status: ExecutionStatus,
        completed_at: datetime,
        duration_ms: int,
        error_type: str | None = None,
        error_code: str | None = None,
        output_digest: str | None = None,
    ) -> ExecutionReceipt:
        """Transition an open (STARTED) receipt to an observed terminal state."""
        if status not in ALLOWED_TERMINAL_STATUSES:
            raise ExecutionReceiptTransitionError(
                f"Status '{status}' is not an allowed executor terminal state; "
                f"expected one of {[s.value for s in ALLOWED_TERMINAL_STATUSES]}"
            )

        with self._lock:
            existing = self._receipts.get(receipt_id)
            if existing is None:
                raise ExecutionReceiptNotFoundError(f"Receipt '{receipt_id}' not found")

            if existing.status != ExecutionStatus.STARTED:
                raise ExecutionReceiptTransitionError(
                    f"Cannot transition receipt '{receipt_id}' from terminal status '{existing.status.value}'"
                )

            terminal_receipt = ExecutionReceipt(
                receipt_id=existing.receipt_id,
                grant_id=existing.grant_id,
                session_id=existing.session_id,
                agent_id=existing.agent_id,
                tool_id=existing.tool_id,
                binding_hash=existing.binding_hash,
                status=status,
                started_at=existing.started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                error_type=error_type,
                error_code=error_code,
                output_digest=output_digest,
            )

            self._receipts[receipt_id] = terminal_receipt
            self._monotonic_starts.pop(receipt_id, None)
            return terminal_receipt

    def record_reconciled(
        self,
        *,
        receipt_id: str,
        reconciled_at: datetime,
        reason: ReconciliationReason,
    ) -> ExecutionReceipt:
        """Transition an open (STARTED) receipt to UNKNOWN via reconciliation authority."""
        with self._lock:
            existing = self._receipts.get(receipt_id)
            if existing is None:
                raise ExecutionReceiptNotFoundError(f"Receipt '{receipt_id}' not found")

            if existing.status != ExecutionStatus.STARTED:
                raise ExecutionReceiptTransitionError(
                    f"Cannot reconcile receipt '{receipt_id}' from terminal status '{existing.status.value}'"
                )

            reconciled_receipt = ExecutionReceipt(
                receipt_id=existing.receipt_id,
                grant_id=existing.grant_id,
                session_id=existing.session_id,
                agent_id=existing.agent_id,
                tool_id=existing.tool_id,
                binding_hash=existing.binding_hash,
                status=ExecutionStatus.UNKNOWN,
                started_at=existing.started_at,
                reconciled_at=reconciled_at,
                reconciliation_reason=reason,
            )

            self._receipts[receipt_id] = reconciled_receipt
            self._monotonic_starts.pop(receipt_id, None)
            return reconciled_receipt

    def get(self, receipt_id: str) -> ExecutionReceipt | None:
        """Retrieve receipt by receipt_id."""
        with self._lock:
            return self._receipts.get(receipt_id)

    def get_by_grant(self, grant_id: str) -> ExecutionReceipt | None:
        """Retrieve receipt associated with a specific grant_id."""
        with self._lock:
            receipt_id = self._grant_to_receipt.get(grant_id)
            if receipt_id is None:
                return None
            return self._receipts.get(receipt_id)

    def get_monotonic_start(self, receipt_id: str) -> float | None:
        """Retrieve recorded monotonic start time for an in-flight receipt."""
        with self._lock:
            return self._monotonic_starts.get(receipt_id)

    def list_open(self) -> tuple[ExecutionReceipt, ...]:
        """List all currently open (STARTED) receipts."""
        with self._lock:
            return tuple(
                r
                for r in self._receipts.values()
                if r.status == ExecutionStatus.STARTED
            )

    def list_receipts(
        self,
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> tuple[ExecutionReceipt, ...]:
        """List receipts matching optional session_id or agent_id filters."""
        with self._lock:
            results = list(self._receipts.values())
            if session_id is not None:
                results = [r for r in results if r.session_id == session_id]
            if agent_id is not None:
                results = [r for r in results if r.agent_id == agent_id]
            return tuple(results)
