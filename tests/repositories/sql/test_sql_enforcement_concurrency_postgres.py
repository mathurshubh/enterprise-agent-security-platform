"""PostgreSQL MVCC concurrency test suite for SqlEnforcementStateRepository (Plane 3, ADR-030).

Authority Note:
While SQLite validates the functional contract (CAS predicates, monotonic increment,
and audit history), PostgreSQL is the concurrency authority. It validates the anchor
lock ordering (agents -> agent_enforcement_state), preventing first-transition races
on pristine agents and subsequent multi-worker CAS contention.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.agent import AgentStatus
from app.models.agent_enforcement import (
    AgentEnforcementState,
    EnforcementAction,
    EnforcementTransition,
)
from app.repositories.sql.base import Base
from app.repositories.sql.enforcement_repository import SqlEnforcementStateRepository
from app.repositories.sql.engine import create_sql_engine, dispose_sql_engine
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.models.enforcement import AgentEnforcementTransitionModel
from app.repositories.sql.session import create_session_factory, transactional_session

POSTGRES_URL = os.environ.get("TEST_DATABASE_URL")
postgres_required = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="PostgreSQL not configured via TEST_DATABASE_URL; concurrency authority suite requires live PostgreSQL",
)


@pytest.fixture
def pg_enforcement_repo():
    """Fixture providing a fresh SqlEnforcementStateRepository connected to PostgreSQL."""
    if not POSTGRES_URL:
        pytest.skip("TEST_DATABASE_URL not configured")

    engine = create_sql_engine(POSTGRES_URL, pool_size=10, max_overflow=10)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    session_factory = create_session_factory(engine)
    now = datetime.now(timezone.utc)

    # Seed test agent
    with transactional_session(session_factory) as db:
        agent = AgentModel(
            agent_id="agent-pg-enf",
            name="PGEnforcementAgent",
            owner="secops@enterprise.internal",
            risk_tier="HIGH",
            status="ACTIVE",
            approved_tools=[],
            created_at=now,
            updated_at=now,
        )
        db.add(agent)

    repo = SqlEnforcementStateRepository(session_factory)
    yield repo, session_factory
    dispose_sql_engine(engine)


@postgres_required
def test_postgres_concurrent_initial_transition_single_winner(pg_enforcement_repo) -> None:
    """Pristine State Race: Concurrent workers competing on epoch 0 -> 1 on uninitialized state.

    Serialization Anchor Invariant:
    Because workers lock the parent agents row first, exactly ONE worker wins the epoch 0 -> 1
    transition. All other concurrent workers read the committed epoch 1 and fail CAS (return False).
    """
    repo, session_factory = pg_enforcement_repo
    agent_id = "agent-pg-enf"
    now = datetime.now(timezone.utc)

    num_workers = 10

    def worker(idx: int) -> bool:
        t = EnforcementTransition(
            transition_id=f"t-init-{idx}",
            agent_id=agent_id,
            action=EnforcementAction.SUSPEND,
            actor=f"worker-{idx}",
            reason="Violation",
            previous_status=AgentStatus.ACTIVE,
            new_status=AgentStatus.SUSPENDED,
            occurred_at=now,
        )
        s = AgentEnforcementState(agent_id=agent_id, epoch=1, suspended_at=now)
        return repo.record_transition(t, s, expected_epoch=0)

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        results = list(executor.map(worker, range(num_workers)))

    # Exactly one worker succeeded
    assert results.count(True) == 1
    assert results.count(False) == num_workers - 1

    # Domain state assertions
    state = repo.get_state(agent_id)
    assert state is not None
    assert state.epoch == 1

    transitions = repo.list_transitions(agent_id)
    assert len(transitions) == 1

    # Relational storage assertions on transition ledger table
    with transactional_session(session_factory) as db:
        db_transitions = db.execute(
            select(AgentEnforcementTransitionModel).where(
                AgentEnforcementTransitionModel.agent_id == agent_id
            )
        ).scalars().all()
        assert len(db_transitions) == 1
        assert db_transitions[0].epoch == 1
        assert not any(t.epoch == 2 for t in db_transitions)


@postgres_required
def test_postgres_concurrent_second_generation_transition_single_winner(
    pg_enforcement_repo,
) -> None:
    """Second-Generation Race: Concurrent workers competing on epoch 1 -> 2 on existing state row."""
    repo, session_factory = pg_enforcement_repo
    agent_id = "agent-pg-enf"
    now = datetime.now(timezone.utc)

    # 1. Establish epoch 1
    t1 = EnforcementTransition(
        transition_id="t-base-1",
        agent_id=agent_id,
        action=EnforcementAction.SUSPEND,
        actor="admin",
        reason="Initial suspension",
        previous_status=AgentStatus.ACTIVE,
        new_status=AgentStatus.SUSPENDED,
        occurred_at=now,
    )
    s1 = AgentEnforcementState(agent_id=agent_id, epoch=1, suspended_at=now)
    assert repo.record_transition(t1, s1, expected_epoch=0) is True

    num_workers = 10

    # 2. Race 10 workers attempting reinstatement epoch 1 -> 2
    def worker(idx: int) -> bool:
        t = EnforcementTransition(
            transition_id=f"t-reinstate-{idx}",
            agent_id=agent_id,
            action=EnforcementAction.REINSTATE,
            actor=f"worker-{idx}",
            reason="Remediation",
            previous_status=AgentStatus.SUSPENDED,
            new_status=AgentStatus.ACTIVE,
            occurred_at=now,
        )
        s = AgentEnforcementState(agent_id=agent_id, epoch=2)
        return repo.record_transition(t, s, expected_epoch=1)

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        results = list(executor.map(worker, range(num_workers)))

    assert results.count(True) == 1
    assert results.count(False) == num_workers - 1

    # Domain state assertions
    state = repo.get_state(agent_id)
    assert state is not None
    assert state.epoch == 2

    transitions = repo.list_transitions(agent_id)
    assert len(transitions) == 2

    # Relational storage assertions on transition ledger table
    with transactional_session(session_factory) as db:
        db_transitions = db.execute(
            select(AgentEnforcementTransitionModel).where(
                AgentEnforcementTransitionModel.agent_id == agent_id
            )
        ).scalars().all()
        assert len(db_transitions) == 2
        epoch_2_transitions = [t for t in db_transitions if t.epoch == 2]
        assert len(epoch_2_transitions) == 1
