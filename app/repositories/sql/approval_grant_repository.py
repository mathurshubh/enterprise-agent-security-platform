"""SQL implementation of ApprovalGrantRepository for ExecutionGrant resumption lifecycle (Plane 3, ADR-031)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.models.execution_grant import (
    ALLOWED_GRANT_TRANSITIONS,
    ExecutionGrant,
    GrantState,
    _deep_unfreeze,
)
from app.repositories.interfaces.approval_grant_repository import (
    ApprovalGrantRepository,
    InvalidGrantTransitionError,
)
from app.repositories.sql.models.execution_grant import ExecutionGrantModel
from app.repositories.sql.session import transactional_session
from app.repositories.sql.session_repository import _ensure_utc


class SqlApprovalGrantRepository(ApprovalGrantRepository):
    """SQLAlchemy implementation of ApprovalGrantRepository for ExecutionGrant lifecycle.

    Invariants:
    - Object Isolation: Stored and returned grants are defensive deep copies (frozen ExecutionGrant domain models).
    - Legal Transitions Only: Strictly enforces ALLOWED_GRANT_TRANSITIONS state machine
      (PENDING -> APPROVED | REJECTED | EXPIRED, APPROVED -> CONSUMED). Illegal transitions raise
      InvalidGrantTransitionError.
    - Exactly-Once Execution Claim: Transition to CONSUMED uses atomic CAS under row-level locking (FOR UPDATE).
      Under concurrent workers, exactly one claim succeeds.
    - State-Specific Field Invariants:
      * PENDING -> APPROVED: requires non-empty approved_by; consumed_at must be None.
      * PENDING -> REJECTED: consumed_at must be None.
      * PENDING -> EXPIRED: approved_by and consumed_at must both be None.
      * APPROVED -> CONSUMED: requires valid consumed_at; approved_by is preserved without overwrite.
    - Deterministic Ordering: list_grants orders by created_at ASC, grant_id ASC.
    - Persistence Authority: get_grant returns the stored grant without evaluating business expiration.
    """

    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    def create_grant(self, grant: ExecutionGrant) -> None:
        with transactional_session(self._session_factory) as db:
            row = ExecutionGrantModel(
                grant_id=grant.grant_id,
                session_id=grant.session_id,
                agent_id=grant.agent_id,
                tool_id=grant.tool_id,
                execution_parameters=_deep_unfreeze(grant.execution_parameters),
                originating_audit_event_id=grant.originating_audit_event_id,
                risk_score=grant.risk_score,
                required_response=grant.required_response,
                enforcement_epoch=grant.enforcement_epoch,
                state=grant.state.value if hasattr(grant.state, "value") else str(grant.state),
                created_at=grant.created_at,
                expires_at=grant.expires_at,
                approved_by=grant.approved_by,
                consumed_at=grant.consumed_at,
            )
            db.add(row)

    def get_grant(self, grant_id: str) -> ExecutionGrant | None:
        with transactional_session(self._session_factory) as db:
            row = db.execute(
                select(ExecutionGrantModel).where(ExecutionGrantModel.grant_id == grant_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return self._to_domain(row)

    def transition_grant(
        self,
        grant_id: str,
        *,
        from_state: GrantState,
        to_state: GrantState,
        consumed_at: datetime | None = None,
        approved_by: str | None = None,
    ) -> bool:
        # Enforce legal transition state machine per ADR-031
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

        with transactional_session(self._session_factory) as db:
            row = db.execute(
                select(ExecutionGrantModel)
                .where(ExecutionGrantModel.grant_id == grant_id)
                .with_for_update()
            ).scalar_one_or_none()

            if row is None or row.state != from_state.value:
                return False

            row.state = to_state.value
            if to_state == GrantState.APPROVED:
                row.approved_by = approved_by
            elif to_state == GrantState.REJECTED:
                if approved_by is not None:
                    row.approved_by = approved_by
            elif to_state == GrantState.CONSUMED:
                row.consumed_at = consumed_at
                # Existing approved_by is intentionally preserved without modification

            return True

    def list_grants(
        self,
        *,
        agent_id: str | None = None,
        state: GrantState | None = None,
    ) -> list[ExecutionGrant]:
        with transactional_session(self._session_factory) as db:
            stmt = select(ExecutionGrantModel)
            if agent_id is not None:
                stmt = stmt.where(ExecutionGrantModel.agent_id == agent_id)
            if state is not None:
                state_val = state.value if hasattr(state, "value") else str(state)
                stmt = stmt.where(ExecutionGrantModel.state == state_val)

            stmt = stmt.order_by(
                ExecutionGrantModel.created_at.asc(),
                ExecutionGrantModel.grant_id.asc(),
            )
            rows = db.execute(stmt).scalars().all()
            return [self._to_domain(r) for r in rows]

    def _to_domain(self, row: ExecutionGrantModel) -> ExecutionGrant:
        return ExecutionGrant(
            grant_id=row.grant_id,
            session_id=row.session_id,
            agent_id=row.agent_id,
            tool_id=row.tool_id,
            execution_parameters=dict(row.execution_parameters or {}),
            originating_audit_event_id=row.originating_audit_event_id,
            risk_score=row.risk_score,
            required_response=row.required_response,
            enforcement_epoch=row.enforcement_epoch,
            state=GrantState(row.state),
            created_at=_ensure_utc(row.created_at),
            expires_at=_ensure_utc(row.expires_at),
            approved_by=row.approved_by,
            consumed_at=_ensure_utc(row.consumed_at),
        )
