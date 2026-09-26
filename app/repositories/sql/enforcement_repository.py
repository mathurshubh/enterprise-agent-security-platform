"""SQL implementation of EnforcementStateRepository with CAS monotonic epoch progression (Plane 3, ADR-030)."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.models.agent import AgentStatus
from app.models.agent_enforcement import (
    AgentEnforcementState,
    EnforcementAction,
    EnforcementTransition,
    EnforcementTrigger,
)
from app.models.risk_assessment import RiskLevel
from app.repositories.interfaces.enforcement_state_repository import (
    EnforcementStateRepository,
    EnforcementStateUnavailableError,
)
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.models.enforcement import (
    AgentEnforcementStateModel,
    AgentEnforcementTransitionModel,
)
from app.repositories.sql.session import transactional_session
from app.repositories.sql.session_repository import _ensure_utc


class SqlEnforcementStateRepository(EnforcementStateRepository):
    """SQLAlchemy implementation of EnforcementStateRepository for agent enforcement state and epoch history.

    Invariants:
    - Object Isolation: Stored and returned entities are defensive domain models.
    - Lock Ordering Invariant:
        1. agents row (AgentModel)
        2. agent_enforcement_state row (AgentEnforcementStateModel)
      All transaction paths acquiring locks on enforcement state must lock the authoritative
      'agents' row first. This guarantees strict serialization even during pristine state creation
      (epoch 0 -> 1) when the enforcement state row does not yet exist.
    - Mandatory CAS Concurrency: record_transition requires expected_epoch matching the persisted epoch.
      On match, atomically updates/creates state, appends transition, and advances epoch to expected_epoch + 1.
      On mismatch, commits no changes and returns False.
    - Pristine State Handling: An agent with no prior enforcement transitions has get_state(agent_id) == None
      and is treated as current_epoch == 0 for CAS evaluation.
    - Deterministic Ordering: list_transitions sorts by (occurred_at ASC, transition_id ASC).
    - Historical Epoch Derivation: get_epoch derives the count of REINSTATE transitions up to as_of
      for detection horizon watermark calculation (distinct from current CAS epoch).
    - Fail-Closed: Infrastructure or database failures raise EnforcementStateUnavailableError.
    """

    def __init__(self, session_factory: sessionmaker[OrmSession]) -> None:
        self._session_factory = session_factory

    def get_state(self, agent_id: str) -> AgentEnforcementState | None:
        try:
            with transactional_session(self._session_factory) as db:
                row = db.execute(
                    select(AgentEnforcementStateModel).where(
                        AgentEnforcementStateModel.agent_id == agent_id
                    )
                ).scalar_one_or_none()
                if row is None:
                    return None
                return AgentEnforcementState(
                    agent_id=row.agent_id,
                    epoch=row.epoch,
                    suspended_at=_ensure_utc(row.suspended_at),
                    suspension_reason=row.suspension_reason,
                    enforcement_baseline_at=_ensure_utc(row.enforcement_baseline_at),
                    enforcement_baseline_sequence=row.enforcement_baseline_sequence,
                    last_transition_at=_ensure_utc(row.last_transition_at),
                )
        except Exception as exc:
            raise EnforcementStateUnavailableError(
                f"Failed to retrieve enforcement state for agent '{agent_id}': {exc}"
            ) from exc

    def record_transition(
        self,
        transition: EnforcementTransition,
        new_state: AgentEnforcementState,
        *,
        expected_epoch: int,
    ) -> bool:
        try:
            with transactional_session(self._session_factory) as db:
                # Lock Ordering Invariant 1: Lock the parent agent row first.
                # This serializes concurrent operations even when agent_enforcement_state row does not exist yet.
                agent_row = db.execute(
                    select(AgentModel)
                    .where(AgentModel.agent_id == transition.agent_id)
                    .with_for_update()
                ).scalar_one_or_none()

                if agent_row is None:
                    raise EnforcementStateUnavailableError(
                        f"Agent '{transition.agent_id}' does not exist; cannot record transition"
                    )

                # Lock Ordering Invariant 2: Lock the enforcement state row second.
                state_row = db.execute(
                    select(AgentEnforcementStateModel)
                    .where(AgentEnforcementStateModel.agent_id == transition.agent_id)
                    .with_for_update()
                ).scalar_one_or_none()

                current_epoch = state_row.epoch if state_row is not None else 0

                # CAS Validation:
                # 1. Expected epoch must match current persisted epoch
                # 2. new_state.epoch must advance by exactly +1
                if current_epoch != expected_epoch or new_state.epoch != expected_epoch + 1:
                    return False

                status_str = "SUSPENDED" if new_state.suspended_at else "ACTIVE"

                if state_row is None:
                    state_row = AgentEnforcementStateModel(
                        agent_id=transition.agent_id,
                        epoch=new_state.epoch,
                        current_status=status_str,
                        suspended_at=new_state.suspended_at,
                        suspension_reason=new_state.suspension_reason,
                        enforcement_baseline_at=new_state.enforcement_baseline_at,
                        enforcement_baseline_sequence=new_state.enforcement_baseline_sequence,
                        last_transition_at=new_state.last_transition_at,
                        updated_at=datetime.now(timezone.utc),
                    )
                    db.add(state_row)
                else:
                    state_row.epoch = new_state.epoch
                    state_row.current_status = status_str
                    state_row.suspended_at = new_state.suspended_at
                    state_row.suspension_reason = new_state.suspension_reason
                    state_row.enforcement_baseline_at = new_state.enforcement_baseline_at
                    state_row.enforcement_baseline_sequence = new_state.enforcement_baseline_sequence
                    state_row.last_transition_at = new_state.last_transition_at
                    state_row.updated_at = datetime.now(timezone.utc)

                trigger = transition.trigger
                transition_row = AgentEnforcementTransitionModel(
                    transition_id=transition.transition_id,
                    agent_id=transition.agent_id,
                    epoch=new_state.epoch,
                    action=(
                        transition.action.value
                        if hasattr(transition.action, "value")
                        else str(transition.action)
                    ),
                    actor=transition.actor,
                    reason=transition.reason,
                    previous_status=(
                        transition.previous_status.value
                        if hasattr(transition.previous_status, "value")
                        else str(transition.previous_status)
                    ),
                    new_status=(
                        transition.new_status.value
                        if hasattr(transition.new_status, "value")
                        else str(transition.new_status)
                    ),
                    trigger_session_id=trigger.session_id if trigger else None,
                    trigger_risk_level=(
                        trigger.risk_level.value
                        if trigger and trigger.risk_level and hasattr(trigger.risk_level, "value")
                        else (str(trigger.risk_level) if trigger and trigger.risk_level else None)
                    ),
                    trigger_risk_score=trigger.risk_score if trigger else None,
                    trigger_finding_ids=list(trigger.finding_ids) if trigger and trigger.finding_ids else None,
                    occurred_at=transition.occurred_at,
                )
                db.add(transition_row)
                return True
        except Exception as exc:
            if isinstance(exc, EnforcementStateUnavailableError):
                raise
            raise EnforcementStateUnavailableError(
                f"Failed to record transition for agent '{transition.agent_id}': {exc}"
            ) from exc

    def list_transitions(
        self,
        agent_id: str | None = None,
    ) -> list[EnforcementTransition]:
        try:
            with transactional_session(self._session_factory) as db:
                stmt = select(AgentEnforcementTransitionModel)
                if agent_id is not None:
                    stmt = stmt.where(AgentEnforcementTransitionModel.agent_id == agent_id)
                stmt = stmt.order_by(
                    AgentEnforcementTransitionModel.occurred_at.asc(),
                    AgentEnforcementTransitionModel.transition_id.asc(),
                )
                rows = db.execute(stmt).scalars().all()
                return [
                    EnforcementTransition(
                        transition_id=r.transition_id,
                        agent_id=r.agent_id,
                        action=EnforcementAction(r.action),
                        actor=r.actor,
                        reason=r.reason,
                        previous_status=AgentStatus(r.previous_status),
                        new_status=AgentStatus(r.new_status),
                        trigger=(
                            EnforcementTrigger(
                                session_id=r.trigger_session_id,
                                risk_level=RiskLevel(r.trigger_risk_level) if r.trigger_risk_level else None,
                                risk_score=r.trigger_risk_score,
                                finding_ids=tuple(r.trigger_finding_ids or ()),
                            )
                            if (r.trigger_session_id or r.trigger_risk_level or r.trigger_risk_score or r.trigger_finding_ids)
                            else None
                        ),
                        occurred_at=_ensure_utc(r.occurred_at),
                    )
                    for r in rows
                ]
        except Exception as exc:
            raise EnforcementStateUnavailableError(
                f"Failed to list transitions: {exc}"
            ) from exc

    def get_epoch(
        self,
        agent_id: str,
        *,
        as_of: datetime,
    ) -> int:
        try:
            with transactional_session(self._session_factory) as db:
                count = db.execute(
                    select(func.count(AgentEnforcementTransitionModel.transition_id)).where(
                        AgentEnforcementTransitionModel.agent_id == agent_id,
                        AgentEnforcementTransitionModel.action == EnforcementAction.REINSTATE.value,
                        AgentEnforcementTransitionModel.occurred_at <= as_of,
                    )
                ).scalar()
                return int(count or 0)
        except Exception as exc:
            raise EnforcementStateUnavailableError(
                f"Failed to compute epoch for agent '{agent_id}': {exc}"
            ) from exc
