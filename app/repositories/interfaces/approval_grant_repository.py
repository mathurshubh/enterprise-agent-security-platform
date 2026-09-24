"""ApprovalGrantRepository — Domain persistence protocol for ExecutionGrant resumption lifecycle (ADR-031)."""

from datetime import datetime
from typing import Protocol

from app.models.execution_grant import ExecutionGrant, GrantState


class InvalidGrantTransitionError(ValueError):
    """Raised when an illegal grant state transition is attempted per ADR-031."""


class ApprovalGrantRepository(Protocol):
    """Repository protocol for ExecutionGrant lifecycle and control-plane resumption (ADR-031).

    Invariants:
    - Legal Transitions Only: Enforces the strict transition state machine
      (PENDING -> APPROVED | REJECTED | EXPIRED, APPROVED -> CONSUMED). Every other transition
      is rejected with InvalidGrantTransitionError.
    - Exactly-Once Claim: transition_grant to CONSUMED is atomic CAS and permits only one
      authorized execution attempt.
    - Zero Untrusted Re-Prompting: Resumption executes the frozen execution_parameters directly.
    """

    def create_grant(self, grant: ExecutionGrant) -> None:
        """Persist a newly created PENDING execution grant."""
        ...

    def get_grant(self, grant_id: str) -> ExecutionGrant | None:
        """Retrieve an execution grant by grant_id, or None if not found."""
        ...

    def transition_grant(
        self,
        grant_id: str,
        *,
        from_state: GrantState,
        to_state: GrantState,
        consumed_at: datetime | None = None,
        approved_by: str | None = None,
    ) -> bool:
        """Atomically transition a grant from from_state to to_state.

        Raises:
            InvalidGrantTransitionError: If the (from_state, to_state) pair is not permitted by ADR-031.

        Returns:
            True if the grant was found in from_state and successfully transitioned to to_state;
            False if the grant was not found or was not in from_state (CAS conflict).
        """
        ...

    def list_grants(
        self,
        *,
        agent_id: str | None = None,
        state: GrantState | None = None,
    ) -> list[ExecutionGrant]:
        """List execution grants with optional filtering by agent_id and/or state."""
        ...
