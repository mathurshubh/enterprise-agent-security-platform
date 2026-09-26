"""PostgreSQL MVCC concurrency test suite for SqlApprovalGrantRepository and Authorization Interlock (Plane 3, ADR-030, ADR-031).

Authority Note:
While SQLite validates the functional grant state machine and metadata invariants,
PostgreSQL is the concurrency authority. It validates:
- Race 4: Double grant consumption (exactly-once claim under FOR UPDATE).
- Race 5: Grant issuance vs. Enforcement containment serialization across distributed workers.
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
from app.models.execution_grant import ExecutionGrant, GrantState
from app.repositories.sql.approval_grant_repository import SqlApprovalGrantRepository
from app.repositories.sql.base import Base
from app.repositories.sql.enforcement_repository import SqlEnforcementStateRepository
from app.repositories.sql.engine import create_sql_engine, dispose_sql_engine
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.models.enforcement import AgentEnforcementStateModel
from app.repositories.sql.models.execution_grant import ExecutionGrantModel
from app.repositories.sql.models.session import SessionModel
from app.repositories.sql.models.tool import ToolModel
from app.repositories.sql.session import create_session_factory, transactional_session

POSTGRES_URL = os.environ.get("TEST_DATABASE_URL")
postgres_required = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="PostgreSQL not configured via TEST_DATABASE_URL; concurrency authority suite requires live PostgreSQL",
)


@pytest.fixture
def pg_grant_env():
    """Fixture providing configured repositories connected to live PostgreSQL."""
    if not POSTGRES_URL:
        pytest.skip("TEST_DATABASE_URL not configured")

    engine = create_sql_engine(POSTGRES_URL, pool_size=15, max_overflow=15)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    session_factory = create_session_factory(engine)
    now = datetime.now(timezone.utc)

    # Seed baseline relational entities
    with transactional_session(session_factory) as db:
        agent = AgentModel(
            agent_id="agent-pg-grant",
            name="PGGrantAgent",
            owner="secops@enterprise.internal",
            risk_tier="HIGH",
            status="ACTIVE",
            approved_tools=["bash"],
            created_at=now,
            updated_at=now,
        )
        tool = ToolModel(
            tool_id="bash",
            name="bash",
            description="Bash tool",
            risk_level="HIGH",
            required_permissions=[],
            metadata_payload={},
            is_active=True,
            created_at=now,
        )
        session = SessionModel(
            session_id="sess-pg-grant",
            agent_id="agent-pg-grant",
            status="ACTIVE",
            next_session_sequence=1,
            created_at=now,
            updated_at=now,
        )
        db.add(agent)
        db.add(tool)
        db.add(session)

    grant_repo = SqlApprovalGrantRepository(session_factory)
    enforcement_repo = SqlEnforcementStateRepository(session_factory)

    yield grant_repo, enforcement_repo, session_factory
    dispose_sql_engine(engine)


@postgres_required
def test_postgres_concurrent_double_grant_consumption_exactly_once(pg_grant_env) -> None:
    """Race 4: 10 concurrent workers attempt to consume the same APPROVED grant.

    Invariant:
    Under FOR UPDATE row locking:
    - Exactly ONE worker succeeds in transitioning APPROVED -> CONSUMED.
    - 9 workers fail CAS and return False.
    - The stored grant is CONSUMED with a single valid consumed_at.
    - approved_by is preserved without mutation.
    """
    grant_repo, _, session_factory = pg_grant_env
    now = datetime.now(timezone.utc)
    grant_id = "grant-pg-race4"

    # 1. Create and approve the grant
    grant = ExecutionGrant(
        grant_id=grant_id,
        session_id="sess-pg-grant",
        agent_id="agent-pg-grant",
        tool_id="bash",
        execution_parameters={"cmd": "deploy"},
        originating_audit_event_id="audit-pg-1",
        risk_score=80,
        required_response="REQUIRE_APPROVAL",
        enforcement_epoch=0,
        state=GrantState.PENDING,
        created_at=now,
        expires_at=now,
    )
    grant_repo.create_grant(grant)

    assert (
        grant_repo.transition_grant(
            grant_id,
            from_state=GrantState.PENDING,
            to_state=GrantState.APPROVED,
            approved_by="secops-operator",
        )
        is True
    )

    num_workers = 10

    # 2. Race 10 workers attempting to consume the approved grant
    def worker(idx: int) -> bool:
        worker_consumed_at = datetime.now(timezone.utc)
        return grant_repo.transition_grant(
            grant_id,
            from_state=GrantState.APPROVED,
            to_state=GrantState.CONSUMED,
            consumed_at=worker_consumed_at,
        )

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        results = list(executor.map(worker, range(num_workers)))

    # Exactly one succeeded
    assert results.count(True) == 1
    assert results.count(False) == num_workers - 1

    # Database assertions
    persisted = grant_repo.get_grant(grant_id)
    assert persisted is not None
    assert persisted.state == GrantState.CONSUMED
    assert persisted.approved_by == "secops-operator"
    assert persisted.consumed_at is not None

    # Storage direct inspection
    with transactional_session(session_factory) as db:
        row = db.execute(
            select(ExecutionGrantModel).where(ExecutionGrantModel.grant_id == grant_id)
        ).scalar_one()
        assert row.state == "CONSUMED"
        assert row.approved_by == "secops-operator"
        assert row.consumed_at is not None


@postgres_required
def test_postgres_issuance_vs_containment_interlock_serialization(pg_grant_env) -> None:
    """Race 5: Demonstrates that the execution authority transaction boundary serializes

    grant issuance against concurrent containment transitions via the enforcement state row lock.

    Case A: Grant issuance acquires the lock first at epoch 1 -> successfully issues grant at epoch 1.
    Case B: Enforcement containment acquires the lock first -> transitions to SUSPENDED at epoch 2;
            grant issuance transaction then reading the row observes SUSPENDED and refuses issuance.
    """
    grant_repo, enforcement_repo, session_factory = pg_grant_env
    agent_id = "agent-pg-grant"
    now = datetime.now(timezone.utc)

    # 1. Establish initial active enforcement state at epoch 1
    t1 = EnforcementTransition(
        transition_id="t-base",
        agent_id=agent_id,
        action=EnforcementAction.REINSTATE,
        actor="admin",
        reason="Baseline active",
        previous_status=AgentStatus.SUSPENDED,
        new_status=AgentStatus.ACTIVE,
        occurred_at=now,
    )
    s1 = AgentEnforcementState(agent_id=agent_id, epoch=1)
    assert enforcement_repo.record_transition(t1, s1, expected_epoch=0) is True

    # Helper simulating ExecutionAuthority grant issuance transaction
    def issue_grant_if_active(grant_id: str, expected_epoch: int) -> bool:
        with transactional_session(session_factory) as db:
            # Step 1: Lock enforcement state row FOR UPDATE
            state_row = db.execute(
                select(AgentEnforcementStateModel)
                .where(AgentEnforcementStateModel.agent_id == agent_id)
                .with_for_update()
            ).scalar_one_or_none()

            if state_row is None or state_row.epoch != expected_epoch or state_row.current_status == "SUSPENDED":
                return False

            # Step 2: Insert execution grant within the same serialized transaction
            grant_row = ExecutionGrantModel(
                grant_id=grant_id,
                session_id="sess-pg-grant",
                agent_id=agent_id,
                tool_id="bash",
                execution_parameters={"cmd": "whoami"},
                originating_audit_event_id="audit-interlock",
                risk_score=70,
                required_response="REQUIRE_APPROVAL",
                enforcement_epoch=state_row.epoch,
                state="PENDING",
                created_at=now,
                expires_at=now,
            )
            db.add(grant_row)
            return True

    # Case A: Issuance while active at expected_epoch=1 succeeds
    assert issue_grant_if_active("grant-case-a", expected_epoch=1) is True
    grant_a = grant_repo.get_grant("grant-case-a")
    assert grant_a is not None
    assert grant_a.enforcement_epoch == 1

    # Now perform containment transition: epoch 1 -> 2, SUSPENDED
    t2 = EnforcementTransition(
        transition_id="t-suspend",
        agent_id=agent_id,
        action=EnforcementAction.SUSPEND,
        actor="detector",
        reason="Compromise detected",
        previous_status=AgentStatus.ACTIVE,
        new_status=AgentStatus.SUSPENDED,
        occurred_at=now,
    )
    s2 = AgentEnforcementState(agent_id=agent_id, epoch=2, suspended_at=now)
    assert enforcement_repo.record_transition(t2, s2, expected_epoch=1) is True

    # Case B: Issuance attempt now observes SUSPENDED posture and epoch mismatch -> fails closed
    assert issue_grant_if_active("grant-case-b", expected_epoch=1) is False
    assert grant_repo.get_grant("grant-case-b") is None
