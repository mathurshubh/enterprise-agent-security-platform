"""InMemoryApprovalGrantRepository — In-memory adapter for ExecutionGrant lifecycle (ADR-031)."""

from datetime import datetime
from threading import RLock

from app.models.execution_grant import (
    ALLOWED_GRANT_TRANSITIONS,
    ExecutionGrant,
    GrantState,
)
from app.repositories.interfaces.approval_grant_repository import (
    ApprovalGrantRepository,
    InvalidGrantTransitionError,
)


class InMemoryApprovalGrantRepository(ApprovalGrantRepository):
    """Thread-safe in-memory repository for ExecutionGrant lifecycle management.

    Invariants:
    - Object Isolation: Stored and returned grants are defensive deep copies.
    - Legal Transitions Only: Enforces ALLOWED_GRANT_TRANSITIONS table.
    - State-Specific Field Invariants:
      * PENDING -> APPROVED: requires non-empty approved_by; consumed_at must be None.
      * PENDING -> REJECTED: consumed_at must be None.
      * PENDING -> EXPIRED: approved_by and consumed_at must both be None.
      * APPROVED -> CONSUMED: requires consumed_at; approved_by is preserved.
    - Immutability: Creates a new frozen ExecutionGrant instance via model_copy.
    - Atomic CAS: Transition succeeds only if persisted state == from_state under RLock.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._grants: dict[str, ExecutionGrant] = {}

    def create_grant(self, grant: ExecutionGrant) -> None:
        with self._lock:
            self._grants[grant.grant_id] = grant.model_copy(deep=True)

    def get_grant(self, grant_id: str) -> ExecutionGrant | None:
        with self._lock:
            grant = self._grants.get(grant_id)
            if grant is None:
                return None
            return grant.model_copy(deep=True)

    def transition_grant(
        self,
        grant_id: str,
        *,
        from_state: GrantState,
        to_state: GrantState,
        consumed_at: datetime | None = None,
        approved_by: str | None = None,
    ) -> bool:
        # Enforce legal transition state machine
        if (from_state, to_state) not in ALLOWED_GRANT_TRANSITIONS:
            raise InvalidGrantTransitionError(
                f"Transition from {from_state} to {to_state} is illegal under ADR-031"
            )

        # Enforce state-specific metadata constraints
        if to_state == GrantState.APPROVED:
            if not approved_by or not approved_by.strip():
                raise InvalidGrantTransitionError(
                    "Transition to APPROVED requires a non-empty approved_by operator"
                )
            if consumed_at is not None:
                raise InvalidGrantTransitionError(
                    "Transition to APPROVED cannot specify consumed_at"
                )
        elif to_state == GrantState.REJECTED:
            if consumed_at is not None:
                raise InvalidGrantTransitionError(
                    "Transition to REJECTED cannot specify consumed_at"
                )
        elif to_state == GrantState.EXPIRED:
            if approved_by is not None or consumed_at is not None:
                raise InvalidGrantTransitionError(
                    "Transition to EXPIRED cannot specify approved_by or consumed_at"
                )
        elif to_state == GrantState.CONSUMED:
            if consumed_at is None:
                raise InvalidGrantTransitionError(
                    "Transition to CONSUMED requires a valid consumed_at timestamp"
                )

        with self._lock:
            grant = self._grants.get(grant_id)
            if grant is None or grant.state != from_state:
                return False

            update_fields: dict[str, object] = {"state": to_state}
            if to_state == GrantState.APPROVED:
                update_fields["approved_by"] = approved_by
            elif to_state == GrantState.REJECTED:
                if approved_by is not None:
                    update_fields["approved_by"] = approved_by
            elif to_state == GrantState.CONSUMED:
                update_fields["consumed_at"] = consumed_at

            updated_grant = grant.model_copy(update=update_fields, deep=True)
            self._grants[grant_id] = updated_grant
            return True

    def list_grants(
        self,
        *,
        agent_id: str | None = None,
        state: GrantState | None = None,
    ) -> list[ExecutionGrant]:
        with self._lock:
            results = list(self._grants.values())
            if agent_id is not None:
                results = [g for g in results if g.agent_id == agent_id]
            if state is not None:
                results = [g for g in results if g.state == state]
            return [g.model_copy(deep=True) for g in results]
