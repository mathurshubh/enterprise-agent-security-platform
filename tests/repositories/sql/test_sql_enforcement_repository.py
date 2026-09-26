"""Contract and verification tests for SqlEnforcementStateRepository (Plane 3, ADR-030)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.agent import AgentStatus
from app.models.agent_enforcement import (
    AgentEnforcementState,
    EnforcementAction,
    EnforcementTransition,
)
from app.repositories.interfaces.enforcement_state_repository import (
    EnforcementStateRepository,
    EnforcementStateUnavailableError,
)
from app.repositories.sql.base import Base
from app.repositories.sql.enforcement_repository import SqlEnforcementStateRepository
from app.repositories.sql.engine import create_sql_engine, dispose_sql_engine
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.models.enforcement import (
    AgentEnforcementStateModel,
    AgentEnforcementTransitionModel,
)
from app.repositories.sql.session import create_session_factory, transactional_session
from tests.repositories.contracts.base_enforcement_contract import (
    BaseEnforcementStateRepositoryContractTests,
)

KNOWN_ENFORCEMENT_AGENTS = [
    "agent-1",
    "agent-cas-1",
    "agent-cas-2",
    "agent-cas-atomicity",
    "agent-iso-enf",
    "agent-monotonic-epoch",
    "agent-order",
    "agent-test-cas",
]


def _seed_enforcement_agents(session_factory) -> None:
    """Seed test agents in the database fixture to satisfy foreign key constraints."""
    now = datetime.now(timezone.utc)
    with transactional_session(session_factory) as db:
        for agent_id in KNOWN_ENFORCEMENT_AGENTS:
            db.merge(
                AgentModel(
                    agent_id=agent_id,
                    name=agent_id,
                    owner="secops@enterprise.internal",
                    risk_tier="LOW",
                    status="ACTIVE",
                    approved_tools=[],
                    created_at=now,
                    updated_at=now,
                )
            )


class TestSqlEnforcementStateRepository(BaseEnforcementStateRepositoryContractTests):
    """Run the exhaustive Plane 1/3 enforcement contract suite against SqlEnforcementStateRepository."""

    def create_repository(self) -> EnforcementStateRepository:
        """Create fresh in-memory SQLite database and seed fixture dependencies."""
        engine = create_sql_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session_factory = create_session_factory(engine)
        _seed_enforcement_agents(session_factory)
        return SqlEnforcementStateRepository(session_factory)


@pytest.fixture
def enforcement_repo_setup():
    """Fixture providing a fresh SqlEnforcementStateRepository and session factory."""
    engine = create_sql_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    _seed_enforcement_agents(session_factory)
    repo = SqlEnforcementStateRepository(session_factory)
    yield repo, session_factory
    dispose_sql_engine(engine)


def test_cas_mismatch_leaves_zero_state_and_zero_transition_mutations(
    enforcement_repo_setup,
) -> None:
    """Verify failed CAS attempt produces neither state mutation nor transition ledger insertion."""
    repo, session_factory = enforcement_repo_setup
    agent_id = "agent-test-cas"
    now = datetime.now(timezone.utc)

    # Attempt CAS with wrong expected_epoch (e.g. 5 instead of 0)
    t = EnforcementTransition(
        transition_id="t-stale",
        agent_id=agent_id,
        action=EnforcementAction.SUSPEND,
        actor="runtime",
        reason="Stale worker",
        previous_status=AgentStatus.ACTIVE,
        new_status=AgentStatus.SUSPENDED,
        occurred_at=now,
    )
    s = AgentEnforcementState(agent_id=agent_id, epoch=6, suspended_at=now)

    assert repo.record_transition(t, s, expected_epoch=5) is False

    # Invariants in storage:
    with transactional_session(session_factory) as db:
        state_row = db.execute(
            select(AgentEnforcementStateModel).where(
                AgentEnforcementStateModel.agent_id == agent_id
            )
        ).scalar_one_or_none()
        assert state_row is None

        transitions = db.execute(
            select(AgentEnforcementTransitionModel).where(
                AgentEnforcementTransitionModel.agent_id == agent_id
            )
        ).scalars().all()
        assert len(transitions) == 0


def test_strict_foreign_key_unknown_agent(enforcement_repo_setup) -> None:
    """Verify that recording a transition for an unregistered agent fails closed."""
    repo, _ = enforcement_repo_setup
    now = datetime.now(timezone.utc)

    t = EnforcementTransition(
        transition_id="t-unknown",
        agent_id="unknown-agent",
        action=EnforcementAction.SUSPEND,
        actor="runtime",
        reason="Violation",
        previous_status=AgentStatus.ACTIVE,
        new_status=AgentStatus.SUSPENDED,
        occurred_at=now,
    )
    s = AgentEnforcementState(agent_id="unknown-agent", epoch=1, suspended_at=now)

    with pytest.raises(EnforcementStateUnavailableError, match="does not exist"):
        repo.record_transition(t, s, expected_epoch=0)
