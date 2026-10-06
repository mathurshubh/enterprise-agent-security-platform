"""SQL administrative plane against the shared contract suite, plus durable specifics."""

from datetime import datetime, timezone

import pytest

from app.models.agent import Agent, RiskTier
from app.models.agent_administrative import (
    Actor,
    AdministrativeAction,
    AdministrativeLifecycleState,
    AdministrativeTransition,
    AgentAdministrativeState,
)
from app.repositories.interfaces.administrative_state_repository import (
    AdministrativeStateRepository,
    AdministrativeStateUnavailableError,
    AdministrativeTransitionInvariantError,
    AgentAlreadyRegisteredError,
)
from app.repositories.sql.administrative_repository import (
    SqlAdministrativeStateRepository,
)
from app.repositories.sql.agent_repository import SqlAgentRepository
from app.repositories.sql.base import Base
from app.repositories.sql.engine import create_sql_engine
from app.repositories.sql.models.administrative import (
    AgentAdministrativeStateModel,
    AgentAdministrativeTransitionModel,
)
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.session import create_session_factory, transactional_session
from tests.repositories.contracts import (
    BaseAdministrativeStateRepositoryContractTests,
)

ADMIN = Actor(type="human", id="sec-ops-1")

# Agents the shared contract suite exercises. The administrative plane locks the parent
# agent row, so every agent a contract test names must exist -- a contract test added
# upstream fails against this adapter until it is listed.
KNOWN_ADMINISTRATIVE_AGENTS = [
    "agent-a",
    "agent-absent",
    "agent-atomic",
    "agent-b",
    "agent-cas",
    "agent-history",
    "agent-invariant",
    "agent-ledger",
    "agent-refusal-atomic",
    "agent-roundtrip",
    "agent-skip",
    "agent-terminal",
    "agent-version-skip",
]


def _seed_agents(session_factory) -> None:
    now = datetime.now(timezone.utc)
    with transactional_session(session_factory) as db:
        for agent_id in KNOWN_ADMINISTRATIVE_AGENTS:
            db.add(
                AgentModel(
                    agent_id=agent_id,
                    name=agent_id,
                    owner="secops@enterprise.internal",
                    risk_tier="LOW",
                    approved_tools=[],
                    created_at=now,
                    updated_at=now,
                )
            )


def _fresh():
    engine = create_sql_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


class TestSqlAdministrativeStateRepository(
    BaseAdministrativeStateRepositoryContractTests
):
    """The same contract the in-memory adapter satisfies, against durable storage."""

    def create_repository(self) -> AdministrativeStateRepository:
        sf = _fresh()
        _seed_agents(sf)
        return SqlAdministrativeStateRepository(sf)


# --- durable specifics the contract suite cannot express --------------------------------


def _registration(agent_id: str):
    now = datetime.now(timezone.utc)
    agent = Agent(
        agent_id=agent_id,
        name=agent_id,
        owner="secops",
        risk_tier=RiskTier.HIGH,
        approved_tools=["file_read"],
    )
    transition = AdministrativeTransition(
        transition_id=f"t-reg-{agent_id}",
        agent_id=agent_id,
        action=AdministrativeAction.REGISTER,
        actor=ADMIN,
        reason="registered",
        previous_state=None,
        new_state=AdministrativeLifecycleState.REGISTERED,
        administrative_version_before=0,
        administrative_version_after=1,
        correlation_id=f"corr-{agent_id}",
        occurred_at=now,
    )
    state = AgentAdministrativeState(
        agent_id=agent_id,
        state=AdministrativeLifecycleState.REGISTERED,
        administrative_version=1,
        last_transition_at=now,
    )
    return agent, transition, state


@pytest.mark.security_invariant
def test_registration_commits_identity_and_administrative_state_together() -> None:
    """The durable composition invariant (F-09.D), stated literally.

    Both rows exist after the call. The point is not that the write succeeded but that the
    two cannot be separated: there is no ordering in which one lands without the other.
    """
    sf = _fresh()
    repo = SqlAdministrativeStateRepository(sf)
    agent, transition, state = _registration("agent-new")

    repo.commit_registration(agent, transition, state)

    with transactional_session(sf) as db:
        assert db.get(AgentModel, "agent-new") is not None
        assert db.get(AgentAdministrativeStateModel, "agent-new") is not None
        assert (
            db.query(AgentAdministrativeTransitionModel)
            .filter_by(agent_id="agent-new")
            .count()
            == 1
        )


@pytest.mark.security_invariant
def test_a_failed_registration_commits_no_agent_at_all() -> None:
    """The invariant is A, not B: no orphaned agent row survives a failed registration.

    This is the property that distinguishes atomic durability from reachability safety. A
    reachability-safe design would leave a committed agent that the application refuses;
    here the agent does not exist, so there is nothing to refuse, reconcile or explain.

    Driven with a transition the invariant checks reject, which fails after the agent row
    has been added to the session but before the transaction commits -- precisely the
    window a two-transaction composition could not close.
    """
    sf = _fresh()
    repo = SqlAdministrativeStateRepository(sf)
    agent, transition, state = _registration("agent-doomed")
    # Registration must commit version 1; offering 2 is an invariant violation.
    bad_state = state.model_copy(update={"administrative_version": 2})

    with pytest.raises(AdministrativeTransitionInvariantError):
        repo.commit_registration(agent, transition, bad_state)

    with transactional_session(sf) as db:
        assert db.get(AgentModel, "agent-doomed") is None
        assert db.get(AgentAdministrativeStateModel, "agent-doomed") is None


@pytest.mark.security_invariant
def test_a_duplicate_registration_is_refused_inside_the_transaction() -> None:
    """Two registrations for one id cannot both commit.

    The existence check runs inside the registration transaction rather than before it, so
    a second registration either sees the first's committed row or loses on the primary
    key -- it cannot observe "absent" after the first has committed.
    """
    sf = _fresh()
    repo = SqlAdministrativeStateRepository(sf)
    agent, transition, state = _registration("agent-dup")
    repo.commit_registration(agent, transition, state)

    with pytest.raises(AgentAlreadyRegisteredError):
        repo.commit_registration(agent, transition, state)

    with transactional_session(sf) as db:
        assert (
            db.query(AgentAdministrativeTransitionModel)
            .filter_by(agent_id="agent-dup")
            .count()
            == 1
        )


@pytest.mark.security_invariant
def test_a_transition_for_an_unknown_agent_is_unavailable_not_refused() -> None:
    """An agent that does not exist cannot have an establishable administrative state.

    Reported as unavailable rather than as an illegal transition, because the two mean
    different things to a caller: one is "this operation is not permitted", the other is
    "nothing can be said about this agent" (L.10).
    """
    sf = _fresh()
    repo = SqlAdministrativeStateRepository(sf)
    _, transition, state = _registration("agent-ghost")

    with pytest.raises(AdministrativeStateUnavailableError):
        repo.record_transition(transition, state, expected_version=0)


def test_the_agent_repository_round_trips_configuration_without_lifecycle_state() -> None:
    """SqlAgentRepository stores identity and configuration only (AP.1)."""
    sf = _fresh()
    repo = SqlAdministrativeStateRepository(sf)
    agents = SqlAgentRepository(sf)
    agent, transition, state = _registration("agent-config")
    repo.commit_registration(agent, transition, state)

    stored = agents.get("agent-config")

    assert stored is not None
    assert stored.name == agent.name
    assert stored.owner == agent.owner
    assert stored.risk_tier is RiskTier.HIGH
    assert stored.approved_tools == ["file_read"]
    # Non-executable: there is no status column, so the model default stands.
    assert stored.status.value == "REGISTERED"
