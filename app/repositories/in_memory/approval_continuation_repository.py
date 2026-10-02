"""InMemoryApprovalContinuationRepository — In-memory adapter for ApprovalContinuation lifecycle (ADR-031)."""

from datetime import datetime
from threading import RLock

from app.models.approval_continuation import (
    ALLOWED_CONTINUATION_TRANSITIONS,
    ApprovalContinuation,
    ContinuationState,
)
from app.repositories.interfaces.approval_continuation_repository import (
    ApprovalContinuationRepository,
    InvalidContinuationTransitionError,
)


class InMemoryApprovalContinuationRepository(ApprovalContinuationRepository):
    """Thread-safe in-memory repository for ApprovalContinuation lifecycle management.

    Invariants:
    - Object Isolation: Stored and returned grants are defensive deep copies.
    - Legal Transitions Only: Enforces ALLOWED_CONTINUATION_TRANSITIONS table.
    - State-Specific Field Invariants:
      * PENDING -> APPROVED: requires non-empty approved_by; consumed_at must be None.
      * PENDING -> REJECTED: consumed_at must be None.
      * PENDING -> EXPIRED: approved_by and consumed_at must both be None.
      * APPROVED -> CONSUMED: requires consumed_at; approved_by is preserved.
    - Immutability: Creates a new frozen ApprovalContinuation instance via model_copy.
    - Atomic CAS: Transition succeeds only if persisted state == from_state under RLock.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._grants: dict[str, ApprovalContinuation] = {}

    def create_continuation(self, grant: ApprovalContinuation) -> None:
        with self._lock:
            self._grants[grant.grant_id] = grant.model_copy(deep=True)

    def get_continuation(self, grant_id: str) -> ApprovalContinuation | None:
        with self._lock:
            grant = self._grants.get(grant_id)
            if grant is None:
                return None
            return grant.model_copy(deep=True)

    def transition_continuation(
        self,
        grant_id: str,
        *,
        from_state: ContinuationState,
        to_state: ContinuationState,
        consumed_at: datetime | None = None,
        approved_by: str | None = None,
    ) -> bool:
        # Enforce legal transition state machine
        if (from_state, to_state) not in ALLOWED_CONTINUATION_TRANSITIONS:
            raise InvalidContinuationTransitionError(
                f"Transition from {from_state} to {to_state} is illegal under ADR-031"
            )

        # Enforce state-specific metadata constraints
        if to_state == ContinuationState.APPROVED:
            if not approved_by or not approved_by.strip():
                raise InvalidContinuationTransitionError(
                    "Transition to APPROVED requires a non-empty approved_by operator"
                )
            if consumed_at is not None:
                raise InvalidContinuationTransitionError(
                    "Transition to APPROVED cannot specify consumed_at"
                )
        elif to_state == ContinuationState.REJECTED:
            if consumed_at is not None:
                raise InvalidContinuationTransitionError(
                    "Transition to REJECTED cannot specify consumed_at"
                )
        elif to_state == ContinuationState.EXPIRED:
            if approved_by is not None or consumed_at is not None:
                raise InvalidContinuationTransitionError(
                    "Transition to EXPIRED cannot specify approved_by or consumed_at"
                )
        elif to_state == ContinuationState.CONSUMED:
            if consumed_at is None:
                raise InvalidContinuationTransitionError(
                    "Transition to CONSUMED requires a valid consumed_at timestamp"
                )

        with self._lock:
            grant = self._grants.get(grant_id)
            if grant is None or grant.state != from_state:
                return False

            update_fields: dict[str, object] = {"state": to_state}
            if to_state == ContinuationState.APPROVED:
                update_fields["approved_by"] = approved_by
            elif to_state == ContinuationState.REJECTED:
                if approved_by is not None:
                    update_fields["approved_by"] = approved_by
            elif to_state == ContinuationState.CONSUMED:
                update_fields["consumed_at"] = consumed_at

            updated_grant = grant.model_copy(update=update_fields, deep=True)
            self._grants[grant_id] = updated_grant
            return True

    def list_continuations(
        self,
        *,
        agent_id: str | None = None,
        state: ContinuationState | None = None,
    ) -> list[ApprovalContinuation]:
        with self._lock:
            results = list(self._grants.values())
            if agent_id is not None:
                results = [g for g in results if g.agent_id == agent_id]
            if state is not None:
                results = [g for g in results if g.state == state]
            return [g.model_copy(deep=True) for g in results]
