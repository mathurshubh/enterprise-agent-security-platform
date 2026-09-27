"""ExecutionEvidenceService — Authoritative in-memory store for execution receipts (ADR-032 §12).

Invariants:
- N3-1 (Receipt Provenance): Identity and binding derived exclusively from verified grant/context.
- N3-4 (Terminal Monotonicity): Terminal execution states are immutable and cannot be transitioned.
- N3-5 (Reconciliation Authority): Transition to UNKNOWN is reserved for reconciliation authority.
- N3-7 (Diagnostic Safety): Raw exception messages excluded.
- N3-9 (Grant Receipt Uniqueness): One receipt per grant_id, over *retained* evidence
  state. This is a provenance/uniqueness property of the evidence index; it is not the
  mechanism preventing re-execution. Single-use grant consumption in ExecutionAuthority
  is what prevents a grant being executed twice, and it holds independently of whether
  the corresponding receipt is still retained.
- N3-10 (UTC Evidence Time): Enforces timezone-aware UTC timestamps.
- N3-11 (Per-Receipt Elapsed Time): Tracks monotonic start per receipt for duration validation.
"""

from datetime import datetime
from threading import RLock

from app.models.execution_evidence_retention import ExecutionEvidenceRetentionPolicy
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

    def __init__(self, retention_policy: ExecutionEvidenceRetentionPolicy) -> None:
        # Two counters are events, not populations, so they cannot be derived from the
        # retained receipts: an evidence failure leaves no receipt, and a reconciled
        # UNKNOWN can be evicted while remaining a fact about what reconciliation did.
        self._evidence_failure_count = 0
        self._reconciled_unknown_count = 0
        # Required, not optional: an unbounded store is not representable, so no wiring
        # omission can produce one in a long-running process.
        self._retention_policy = retention_policy
        self._lock = RLock()
        self._receipts: dict[str, ExecutionReceipt] = {}
        self._grant_to_receipt: dict[str, str] = {}
        self._monotonic_starts: dict[str, float] = {}

    @property
    def retention_policy(self) -> ExecutionEvidenceRetentionPolicy:
        return self._retention_policy

    @property
    def open_receipt_count(self) -> int:
        """Receipts currently in STARTED.

        Derived from authoritative state under the lock rather than tracked
        independently, so no lifecycle or eviction path can leave it disagreeing with
        the receipts themselves. Persistent growth here is the signal for an evidence
        fault that retention deliberately does not absorb.
        """
        with self._lock:
            return sum(
                1
                for r in self._receipts.values()
                if r.status == ExecutionStatus.STARTED
            )

    @property
    def terminal_receipt_count(self) -> int:
        """Retained terminal receipts, including UNKNOWN. Bounded by retention."""
        with self._lock:
            return sum(
                1
                for r in self._receipts.values()
                if r.status != ExecutionStatus.STARTED
            )

    @property
    def evidence_failure_count(self) -> int:
        """Evidence *persistence* failures, never execution failures.

        A transition rejected because the receipt already reached a terminal state is
        not counted: that is the expected self-resolution race, and treating it as an
        evidence fault would make ordinary concurrency look like an integrity problem.
        """
        with self._lock:
            return self._evidence_failure_count

    @property
    def reconciled_unknown_count(self) -> int:
        """Executions reconciliation actually resolved to UNKNOWN.

        Counted at the transition rather than inferred from receipts currently holding
        that status, because a reconciled receipt can later be evicted and because
        UNKNOWN is only ever reached through reconciliation.
        """
        with self._lock:
            return self._reconciled_unknown_count

    def _prune_terminal_locked(self) -> None:
        """Evict oldest terminal receipts beyond the configured bound.

        Called only after a receipt reaches a terminal state, never on record_started:
        the bound is on terminal evidence, so a long-running or orphaned STARTED receipt
        stays available to the reconciler however many terminal receipts exist.

        Every structure keyed by the evicted receipt is pruned in the same critical
        section. Bounding ``_receipts`` alone would leave the grant index and the
        monotonic-start map growing without limit, so the store would remain unbounded
        while appearing bounded.
        """
        terminal = [
            receipt
            for receipt in self._receipts.values()
            if receipt.status != ExecutionStatus.STARTED
        ]
        excess = len(terminal) - self._retention_policy.max_terminal_receipts
        if excess <= 0:
            return

        # Oldest-first. sorted() is stable, so receipts sharing a started_at are evicted
        # in insertion order rather than arbitrarily.
        for receipt in sorted(terminal, key=lambda r: r.started_at)[:excess]:
            self._receipts.pop(receipt.receipt_id, None)
            self._grant_to_receipt.pop(receipt.grant_id, None)
            self._monotonic_starts.pop(receipt.receipt_id, None)

    def record_started(
        self,
        *,
        receipt_id: str,
        grant_id: str,
        session_id: str,
        agent_id: str,
        request_id: str,
        tool_id: str,
        binding_hash: str,
        capability_profile_id: str,
        capability_digest: str,
        declared_timeout_seconds: float,
        started_at: datetime,
        monotonic_start: float | None = None,
    ) -> ExecutionReceipt:
        """Record the initial STARTED receipt at the tool execution boundary."""
        with self._lock:
            if receipt_id in self._receipts:
                self._evidence_failure_count += 1
                raise ExecutionReceiptDuplicateError(
                    f"Execution receipt '{receipt_id}' already exists"
                )

            if grant_id in self._grant_to_receipt:
                self._evidence_failure_count += 1
                raise ExecutionReceiptDuplicateError(
                    f"Grant '{grant_id}' is already bound to receipt '{self._grant_to_receipt[grant_id]}'"
                )

            receipt = ExecutionReceipt(
                receipt_id=receipt_id,
                grant_id=grant_id,
                session_id=session_id,
                agent_id=agent_id,
                request_id=request_id,
                tool_id=tool_id,
                binding_hash=binding_hash,
                capability_profile_id=capability_profile_id,
                capability_digest=capability_digest,
                declared_timeout_seconds=declared_timeout_seconds,
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
                request_id=existing.request_id,
                tool_id=existing.tool_id,
                binding_hash=existing.binding_hash,
                capability_profile_id=existing.capability_profile_id,
                capability_digest=existing.capability_digest,
                declared_timeout_seconds=existing.declared_timeout_seconds,
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
            self._prune_terminal_locked()
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
                request_id=existing.request_id,
                tool_id=existing.tool_id,
                binding_hash=existing.binding_hash,
                capability_profile_id=existing.capability_profile_id,
                capability_digest=existing.capability_digest,
                declared_timeout_seconds=existing.declared_timeout_seconds,
                status=ExecutionStatus.UNKNOWN,
                started_at=existing.started_at,
                reconciled_at=reconciled_at,
                reconciliation_reason=reason,
            )

            self._receipts[receipt_id] = reconciled_receipt
            self._reconciled_unknown_count += 1
            self._monotonic_starts.pop(receipt_id, None)
            # UNKNOWN is terminal, so a reconciled receipt is subject to the same bound.
            self._prune_terminal_locked()
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
