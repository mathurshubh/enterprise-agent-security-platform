"""SQL adapters for the administrative lifecycle plane (ADR-030 L.3, AP.3/AP.4/AP.11)."""

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.models.administrative_audit_event import (
    AdministrativeAuditEvent,
    AdministrativeRefusalCode,
)
from app.models.agent import Agent
from app.models.agent_administrative import (
    Actor,
    ActorType,
    AdministrativeAction,
    AdministrativeLifecycleState,
    AdministrativeTransition,
    AgentAdministrativeState,
    is_legal_administrative_transition,
)
from app.repositories.interfaces.administrative_audit_repository import (
    AdministrativeAuditRepository,
    AdministrativeAuditUnavailableError,
)
from app.repositories.interfaces.administrative_state_repository import (
    AdministrativeStateRepository,
    AdministrativeStateUnavailableError,
    AdministrativeTransitionInvariantError,
    AgentAlreadyRegisteredError,
)
from app.repositories.sql.models.administrative import (
    AdministrativeAuditEventModel,
    AgentAdministrativeStateModel,
    AgentAdministrativeTransitionModel,
)
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.session import transactional_session
from app.repositories.sql.session_repository import _ensure_utc


def _state_to_domain(row: AgentAdministrativeStateModel) -> AgentAdministrativeState:
    return AgentAdministrativeState(
        agent_id=row.agent_id,
        state=AdministrativeLifecycleState(row.state),
        administrative_version=row.administrative_version,
        # Reusing the existing helper rather than adding a second: SQLite returns naive
        # datetimes, and a dropped tzinfo is not cosmetic -- comparing naive with aware
        # raises, so B-13's recorded_at/baseline_at check would crash rather than fail.
        last_transition_at=_ensure_utc(row.last_transition_at),
    )


def _transition_to_domain(
    row: AgentAdministrativeTransitionModel,
) -> AdministrativeTransition:
    return AdministrativeTransition(
        transition_id=row.transition_id,
        agent_id=row.agent_id,
        action=AdministrativeAction(row.action),
        actor=Actor(type=ActorType(row.actor_type), id=row.actor_id),
        reason=row.reason,
        previous_state=(
            None
            if row.previous_state is None
            else AdministrativeLifecycleState(row.previous_state)
        ),
        new_state=AdministrativeLifecycleState(row.new_state),
        administrative_version_before=row.administrative_version_before,
        administrative_version_after=row.administrative_version_after,
        correlation_id=row.correlation_id,
        occurred_at=_ensure_utc(row.occurred_at),
    )


class SqlAdministrativeStateRepository(AdministrativeStateRepository):
    """Durable administrative lifecycle state and ledger.

    Reproduces the in-memory adapter's semantics with durable row locking rather than a
    process lock, which ADR-024 A.6 requires: process-local locks may reduce contention
    but are never the correctness mechanism.

    Lock ordering follows the enforcement plane's: the ``agents`` row first, then the
    administrative state row. ``agents`` is the identity record and the parent-lock anchor
    for both lifecycle planes (L.3), so taking it first keeps the two planes from
    deadlocking against each other.
    """

    def __init__(self, session_factory: sessionmaker[OrmSession] | OrmSession) -> None:
        self._session_factory = session_factory

    def get_state(self, agent_id: str) -> AgentAdministrativeState | None:
        try:
            with transactional_session(self._session_factory) as db:
                row = db.get(AgentAdministrativeStateModel, agent_id)
                return None if row is None else _state_to_domain(row)
        except Exception as exc:
            raise AdministrativeStateUnavailableError(
                f"Administrative state repository unavailable for agent '{agent_id}': {exc}"
            ) from exc

    def record_transition(
        self,
        transition: AdministrativeTransition,
        new_state: AgentAdministrativeState,
        *,
        expected_version: int,
    ) -> bool:
        agent_id = transition.agent_id
        try:
            with transactional_session(self._session_factory) as db:
                # Lock ordering 1: the identity record, the anchor for both planes.
                #
                # The existence check below is NOT what makes a transition for an unknown
                # agent fail -- the foreign key would reject it anyway, and mutation
                # testing confirmed as much by producing an equivalent mutant. What this
                # statement provides is the `FOR UPDATE` lock, taken on `agents` before
                # the administrative row, in the same order the enforcement plane uses.
                # Two planes locking one agent in opposite orders is a deadlock, and no
                # SQLite test can observe that, so the ordering is kept deliberately
                # rather than defended by a test.
                agent_row = db.execute(
                    select(AgentModel)
                    .where(AgentModel.agent_id == agent_id)
                    .with_for_update()
                ).scalar_one_or_none()
                if agent_row is None:
                    raise AdministrativeStateUnavailableError(
                        f"Agent '{agent_id}' does not exist; cannot record an "
                        f"administrative transition"
                    )

                # Lock ordering 2: the administrative state row.
                state_row = db.execute(
                    select(AgentAdministrativeStateModel)
                    .where(AgentAdministrativeStateModel.agent_id == agent_id)
                    .with_for_update()
                ).scalar_one_or_none()

                current_version = (
                    state_row.administrative_version if state_row is not None else 0
                )

                # Compare-and-set first. A mismatch is a lost update: another transition
                # committed since the caller read, and re-reading repairs it.
                if current_version != expected_version:
                    return False

                _validate_transition_invariants(
                    agent_id=agent_id,
                    transition=transition,
                    new_state=new_state,
                    current_version=current_version,
                    previous_state=(
                        None
                        if state_row is None
                        else AdministrativeLifecycleState(state_row.state)
                    ),
                    expected_version=expected_version,
                )

                if state_row is None:
                    db.add(
                        AgentAdministrativeStateModel(
                            agent_id=agent_id,
                            state=new_state.state.value,
                            administrative_version=new_state.administrative_version,
                            last_transition_at=new_state.last_transition_at,
                        )
                    )
                else:
                    state_row.state = new_state.state.value
                    state_row.administrative_version = new_state.administrative_version
                    state_row.last_transition_at = new_state.last_transition_at

                db.add(
                    AgentAdministrativeTransitionModel(
                        transition_id=transition.transition_id,
                        agent_id=agent_id,
                        action=transition.action.value,
                        actor_type=transition.actor.type.value,
                        actor_id=transition.actor.id,
                        reason=transition.reason,
                        previous_state=(
                            None
                            if transition.previous_state is None
                            else transition.previous_state.value
                        ),
                        new_state=transition.new_state.value,
                        administrative_version_before=(
                            transition.administrative_version_before
                        ),
                        administrative_version_after=(
                            transition.administrative_version_after
                        ),
                        correlation_id=transition.correlation_id,
                        occurred_at=transition.occurred_at,
                    )
                )
                return True
        except (
            AdministrativeTransitionInvariantError,
            AdministrativeStateUnavailableError,
        ):
            raise
        except Exception as exc:
            raise AdministrativeStateUnavailableError(
                f"Administrative transition failed for agent '{agent_id}': {exc}"
            ) from exc

    def commit_registration(
        self,
        agent: Agent,
        transition: AdministrativeTransition,
        new_state: AgentAdministrativeState,
    ) -> None:
        """Create the agent row, its administrative state and the ledger entry, atomically.

        Three tables, one transaction -- the same shape ``record_transition`` already uses
        for state plus ledger, extended to include the identity row the foreign key
        requires. On any failure the transaction rolls back and no agent exists, so the
        durable invariant holds literally rather than by a fail-closed read.

        The existence check runs inside the transaction. Checking beforehand would let two
        concurrent registrations both observe "absent"; here the second either sees the
        first's committed row or loses on the primary key.
        """
        try:
            with transactional_session(self._session_factory) as db:
                if db.get(AgentModel, agent.agent_id) is not None:
                    raise AgentAlreadyRegisteredError(
                        f"Agent '{agent.agent_id}' already exists"
                    )

                _validate_transition_invariants(
                    agent_id=agent.agent_id,
                    transition=transition,
                    new_state=new_state,
                    current_version=0,
                    previous_state=None,
                    expected_version=0,
                )

                db.add(
                    AgentModel(
                        agent_id=agent.agent_id,
                        name=agent.name,
                        owner=agent.owner,
                        risk_tier=(
                            agent.risk_tier.value
                            if hasattr(agent.risk_tier, "value")
                            else str(agent.risk_tier)
                        ),
                        approved_tools=list(agent.approved_tools),
                    )
                )
                db.flush()  # the foreign keys below require the identity row to exist

                db.add(
                    AgentAdministrativeStateModel(
                        agent_id=agent.agent_id,
                        state=new_state.state.value,
                        administrative_version=new_state.administrative_version,
                        last_transition_at=new_state.last_transition_at,
                    )
                )
                db.add(
                    AgentAdministrativeTransitionModel(
                        transition_id=transition.transition_id,
                        agent_id=agent.agent_id,
                        action=transition.action.value,
                        actor_type=transition.actor.type.value,
                        actor_id=transition.actor.id,
                        reason=transition.reason,
                        previous_state=None,
                        new_state=transition.new_state.value,
                        administrative_version_before=0,
                        administrative_version_after=(
                            transition.administrative_version_after
                        ),
                        correlation_id=transition.correlation_id,
                        occurred_at=transition.occurred_at,
                    )
                )
        except (
            AgentAlreadyRegisteredError,
            AdministrativeTransitionInvariantError,
        ):
            raise
        except Exception as exc:
            raise AdministrativeStateUnavailableError(
                f"Registration failed for agent '{agent.agent_id}': {exc}"
            ) from exc

    def list_transitions(
        self,
        agent_id: str | None = None,
    ) -> list[AdministrativeTransition]:
        try:
            with transactional_session(self._session_factory) as db:
                stmt = select(AgentAdministrativeTransitionModel)
                if agent_id is not None:
                    stmt = stmt.where(
                        AgentAdministrativeTransitionModel.agent_id == agent_id
                    )
                stmt = stmt.order_by(
                    AgentAdministrativeTransitionModel.occurred_at.asc(),
                    AgentAdministrativeTransitionModel.transition_id.asc(),
                )
                return [_transition_to_domain(r) for r in db.execute(stmt).scalars()]
        except Exception as exc:
            raise AdministrativeStateUnavailableError(
                f"Administrative ledger unavailable: {exc}"
            ) from exc


def _validate_transition_invariants(
    *,
    agent_id: str,
    transition: AdministrativeTransition,
    new_state: AgentAdministrativeState,
    current_version: int,
    previous_state: AdministrativeLifecycleState | None,
    expected_version: int,
) -> None:
    """Refuse anything that is an invariant violation rather than a lost race (AP.4).

    Identical in substance to the in-memory adapter's checks, and shared by the contract
    suite. Several are also expressed as schema constraints; both are kept because a CHECK
    cannot produce a domain error naming the states, and a Python check cannot stop a write
    that reaches the table by another route.
    """
    if new_state.administrative_version != expected_version + 1:
        raise AdministrativeTransitionInvariantError(
            f"Administrative version must advance by exactly one for agent "
            f"'{agent_id}': expected {expected_version + 1}, offered "
            f"{new_state.administrative_version}."
        )

    if not is_legal_administrative_transition(previous_state, new_state.state):
        raise AdministrativeTransitionInvariantError(
            f"Illegal administrative transition for agent '{agent_id}': "
            f"{previous_state.value if previous_state else 'none'} -> "
            f"{new_state.state.value}."
        )

    if (
        transition.previous_state != previous_state
        or transition.new_state != new_state.state
        or transition.administrative_version_before != current_version
        or transition.administrative_version_after != new_state.administrative_version
    ):
        raise AdministrativeTransitionInvariantError(
            f"Ledger entry does not describe the transition being committed for agent "
            f"'{agent_id}'. A ledger that disagrees with the state it records is not "
            f"evidence of it."
        )


class SqlAdministrativeAuditRepository(AdministrativeAuditRepository):
    """Durable append-only store for refused administrative attempts."""

    def __init__(self, session_factory: sessionmaker[OrmSession] | OrmSession) -> None:
        self._session_factory = session_factory

    def record_event(self, event: AdministrativeAuditEvent) -> AdministrativeAuditEvent:
        try:
            with transactional_session(self._session_factory) as db:
                db.add(
                    AdministrativeAuditEventModel(
                        event_id=event.event_id,
                        agent_id=event.agent_id,
                        attempted_action=event.attempted_action.value,
                        actor_type=event.actor.type.value,
                        actor_id=event.actor.id,
                        refusal_code=event.refusal_code.value,
                        reason=event.reason,
                        observed_state=(
                            None
                            if event.observed_state is None
                            else event.observed_state.value
                        ),
                        correlation_id=event.correlation_id,
                        occurred_at=event.occurred_at,
                    )
                )
            return event
        except Exception as exc:
            # Its own error: L.10 requires the caller to return 503, commit no
            # administrative mutation, and never imply the refusal was recorded.
            raise AdministrativeAuditUnavailableError(
                f"Administrative refusal evidence could not be persisted: {exc}"
            ) from exc

    def list_events(
        self,
        agent_id: str | None = None,
    ) -> list[AdministrativeAuditEvent]:
        try:
            with transactional_session(self._session_factory) as db:
                stmt = select(AdministrativeAuditEventModel)
                if agent_id is not None:
                    stmt = stmt.where(AdministrativeAuditEventModel.agent_id == agent_id)
                stmt = stmt.order_by(
                    AdministrativeAuditEventModel.occurred_at.asc(),
                    AdministrativeAuditEventModel.event_id.asc(),
                )
                return [
                    AdministrativeAuditEvent(
                        event_id=r.event_id,
                        agent_id=r.agent_id,
                        attempted_action=AdministrativeAction(r.attempted_action),
                        actor=Actor(type=ActorType(r.actor_type), id=r.actor_id),
                        refusal_code=AdministrativeRefusalCode(r.refusal_code),
                        reason=r.reason,
                        observed_state=(
                            None
                            if r.observed_state is None
                            else AdministrativeLifecycleState(r.observed_state)
                        ),
                        correlation_id=r.correlation_id,
                        occurred_at=_ensure_utc(r.occurred_at),
                    )
                    for r in db.execute(stmt).scalars()
                ]
        except Exception as exc:
            raise AdministrativeAuditUnavailableError(
                f"Administrative refusal evidence unavailable: {exc}"
            ) from exc
