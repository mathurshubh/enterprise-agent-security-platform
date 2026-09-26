"""Contract and verification tests for SqlApprovalGrantRepository (Plane 3, ADR-030, ADR-031)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.execution_grant import ExecutionGrant, GrantState
from app.repositories.interfaces.approval_grant_repository import (
    ApprovalGrantRepository,
    InvalidGrantTransitionError,
)
from app.repositories.sql.approval_grant_repository import SqlApprovalGrantRepository
from app.repositories.sql.base import Base
from app.repositories.sql.engine import create_sql_engine, dispose_sql_engine
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.models.execution_grant import ExecutionGrantModel
from app.repositories.sql.models.session import SessionModel
from app.repositories.sql.models.tool import ToolModel
from app.repositories.sql.session import create_session_factory, transactional_session
from tests.repositories.contracts.base_approval_grant_contract import (
    BaseApprovalGrantRepositoryContractTests,
)

KNOWN_GRANT_AGENTS = ["agent-1", "a-1", "a-2"]
KNOWN_GRANT_TOOLS = ["bash", "file_read"]
KNOWN_GRANT_SESSIONS = ["sess-1"]


def _seed_grant_dependencies(session_factory) -> None:
    """Seed test agents, sessions, and tools in database fixture."""
    now = datetime.now(timezone.utc)
    with transactional_session(session_factory) as db:
        for agent_id in KNOWN_GRANT_AGENTS:
            db.merge(
                AgentModel(
                    agent_id=agent_id,
                    name=agent_id,
                    owner="secops@enterprise.internal",
                    risk_tier="LOW",
                    status="ACTIVE",
                    approved_tools=KNOWN_GRANT_TOOLS,
                    created_at=now,
                    updated_at=now,
                )
            )
        for tool_id in KNOWN_GRANT_TOOLS:
            db.merge(
                ToolModel(
                    tool_id=tool_id,
                    name=tool_id,
                    description="Test tool",
                    risk_level="LOW",
                    required_permissions=[],
                    metadata_payload={},
                    is_active=True,
                    created_at=now,
                )
            )
        for session_id in KNOWN_GRANT_SESSIONS:
            db.merge(
                SessionModel(
                    session_id=session_id,
                    agent_id="agent-1",
                    status="ACTIVE",
                    next_session_sequence=1,
                    created_at=now,
                    updated_at=now,
                )
            )


class TestSqlApprovalGrantRepository(BaseApprovalGrantRepositoryContractTests):
    """Run the exhaustive ADR-031 approval grant contract suite against SqlApprovalGrantRepository."""

    def create_repository(self) -> ApprovalGrantRepository:
        """Create fresh in-memory SQLite database and seed fixture dependencies."""
        engine = create_sql_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session_factory = create_session_factory(engine)
        _seed_grant_dependencies(session_factory)
        return SqlApprovalGrantRepository(session_factory)


@pytest.fixture
def grant_repo_setup():
    """Fixture providing a configured SqlApprovalGrantRepository and session factory."""
    engine = create_sql_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    _seed_grant_dependencies(session_factory)
    repo = SqlApprovalGrantRepository(session_factory)
    yield repo, session_factory
    dispose_sql_engine(engine)


def test_illegal_state_transitions_raise_error(grant_repo_setup) -> None:
    """Verify illegal transitions (e.g. PENDING -> CONSUMED) raise InvalidGrantTransitionError."""
    repo, _ = grant_repo_setup
    now = datetime.now(timezone.utc)
    grant = ExecutionGrant(
        grant_id="grant-illegal",
        session_id="sess-1",
        agent_id="agent-1",
        tool_id="bash",
        execution_parameters={"cmd": "ls"},
        originating_audit_event_id="audit-1",
        risk_score=50,
        required_response="REQUIRE_APPROVAL",
        enforcement_epoch=0,
        state=GrantState.PENDING,
        created_at=now,
        expires_at=now,
    )
    repo.create_grant(grant)

    with pytest.raises(InvalidGrantTransitionError):
        repo.transition_grant(
            "grant-illegal",
            from_state=GrantState.PENDING,
            to_state=GrantState.CONSUMED,
            consumed_at=now,
        )


def test_atomic_cas_failure_leaves_grant_unmutated(grant_repo_setup) -> None:
    """Verify CAS mismatch leaves state and metadata unmutated in database."""
    repo, session_factory = grant_repo_setup
    now = datetime.now(timezone.utc)
    grant = ExecutionGrant(
        grant_id="grant-cas-fail",
        session_id="sess-1",
        agent_id="agent-1",
        tool_id="bash",
        execution_parameters={"cmd": "whoami"},
        originating_audit_event_id="audit-1",
        risk_score=60,
        required_response="REQUIRE_APPROVAL",
        enforcement_epoch=0,
        state=GrantState.PENDING,
        created_at=now,
        expires_at=now,
    )
    repo.create_grant(grant)

    # Attempt CAS from APPROVED when current state is PENDING
    assert (
        repo.transition_grant(
            "grant-cas-fail",
            from_state=GrantState.APPROVED,
            to_state=GrantState.CONSUMED,
            consumed_at=now,
        )
        is False
    )

    # Verify storage remains PENDING with None consumed_at
    with transactional_session(session_factory) as db:
        row = db.execute(
            select(ExecutionGrantModel).where(ExecutionGrantModel.grant_id == "grant-cas-fail")
        ).scalar_one()
        assert row.state == "PENDING"
        assert row.consumed_at is None
        assert row.approved_by is None


def test_strict_foreign_keys_on_grant_creation(grant_repo_setup) -> None:
    """Verify creating a grant referencing an unknown entity fails closed with IntegrityError."""
    repo, _ = grant_repo_setup
    now = datetime.now(timezone.utc)

    # Unknown agent
    invalid_grant = ExecutionGrant(
        grant_id="grant-invalid-agent",
        session_id="sess-1",
        agent_id="nonexistent-agent",
        tool_id="bash",
        execution_parameters={},
        originating_audit_event_id="audit-1",
        risk_score=10,
        required_response="REQUIRE_APPROVAL",
        enforcement_epoch=0,
        state=GrantState.PENDING,
        created_at=now,
        expires_at=now,
    )
    with pytest.raises(IntegrityError):
        repo.create_grant(invalid_grant)
