"""ApprovalContinuationRepository — Domain persistence protocol for ApprovalContinuation resumption lifecycle (ADR-031)."""

from datetime import datetime
from typing import Protocol

from app.models.approval_continuation import ApprovalContinuation, ContinuationState


class InvalidContinuationTransitionError(ValueError):
    """Raised when an illegal grant state transition is attempted per ADR-031."""


class ApprovalContinuationRepository(Protocol):
    """Repository protocol for ApprovalContinuation lifecycle and control-plane resumption (ADR-031).

    Invariants:
    - Legal Transitions Only: Enforces the strict transition state machine
      (PENDING -> APPROVED | REJECTED | EXPIRED, APPROVED -> CONSUMED). Every other transition
      is rejected with InvalidContinuationTransitionError.
    - Exactly-Once Claim: transition_continuation to CONSUMED is atomic CAS and permits only one
      authorized execution attempt.
    - Zero Untrusted Re-Prompting: Resumption executes the frozen execution_parameters directly.
    """

    def create_continuation(self, grant: ApprovalContinuation) -> None:
        """Persist a newly created PENDING execution grant."""
        ...

    def get_continuation(self, grant_id: str) -> ApprovalContinuation | None:
        """Retrieve an execution grant by grant_id, or None if not found."""
        ...

    def transition_continuation(
        self,
        grant_id: str,
        *,
        from_state: ContinuationState,
        to_state: ContinuationState,
        consumed_at: datetime | None = None,
        approved_by: str | None = None,
    ) -> bool:
        """Atomically transition a grant from from_state to to_state.

        Raises:
            InvalidContinuationTransitionError: If the (from_state, to_state) pair is not permitted by ADR-031.

        Returns:
            True if the grant was found in from_state and successfully transitioned to to_state;
            False if the grant was not found or was not in from_state (CAS conflict).
        """
        ...

    def list_continuations(
        self,
        *,
        agent_id: str | None = None,
        state: ContinuationState | None = None,
    ) -> list[ApprovalContinuation]:
        """List execution grants with optional filtering by agent_id and/or state."""
        ...
