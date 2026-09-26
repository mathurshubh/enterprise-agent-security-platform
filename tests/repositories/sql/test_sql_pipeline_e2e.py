"""SQL-backed end-to-end security pipeline verification (Plane 3, Step 6C).

Validates the full authorization -> detection horizon -> risk -> response -> execution path
using the concrete SQL repository adapters:
- Case 1: ALLOW path produces grant, exactly-once execution succeeds, second claim fails
- Case 2: SUSPENDED agent halts authorization, issues no grant, fails execution
- Case 3: Stale enforcement epoch between authorization and issuance fails closed at the authority boundary
- Case 4: Stale already-issued grant cannot execute after agent containment
- Case 5: Durable human-in-the-loop ExecutionGrant resumption with atomic exactly-once claim
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session as OrmSession

from app.auth.authorization_service import AuthorizationService
from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.audit_event import Decision
from app.models.execution_binding import ExecutionBinding
from app.models.execution_grant import ExecutionGrant, GrantState
from app.models.session_event import SessionEvent
from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_descriptor import ToolDescriptor
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.policy.policy_engine import PolicyEngine
from app.repositories import create_repositories
from app.repositories.sql.base import Base
from app.repositories.sql.engine import create_sql_engine, dispose_sql_engine
from app.repositories.sql.models.agent import AgentModel
from app.repositories.sql.models.tool import ToolModel
from app.runtime.execution_authority import (
    ExecutionAuthority,
    ExecutionBindingError,
    ExecutionRefusalReason,
)
from app.runtime.tool_executor import DefaultToolExecutor
from app.services.agent_service import AgentService
from app.services.session_service import SessionService
from app.services.tool_service import ToolService
from app.tools.base_tool import BaseTool


class MockTestTool(BaseTool):
    """Simple test tool for execution verification."""

    def __init__(self, tool_id: str = "file_read") -> None:
        self.executions = 0
        self._metadata = ToolMetadata(
            identity=ToolIdentity(
                tool_id=tool_id,
                name="Test File Read Tool",
                version="1.0.0",
                description="Mock tool for E2E tests",
            ),
            governance=ToolGovernance(risk_level=ToolRiskLevel.LOW),
            capability=ToolCapability(category="filesystem"),
            operational=ToolOperational(),
        )

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def execute(self, parameters: dict[str, object]) -> dict[str, object]:
        self.executions += 1
        return {"status": "success", "params": parameters}


@pytest.fixture
def sql_pipeline_setup():
    """Build a complete, isolated SQL-backed pipeline test harness."""
    engine = create_sql_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    container = create_repositories(backend="sql", engine=engine)

    # Seed SQL DB parent rows for referential integrity
    with OrmSession(engine) as session:
        session.add(
            AgentModel(
                agent_id="agent-e2e",
                name="E2E Agent",
                owner="security",
                risk_tier="LOW",
                status="ACTIVE",
            )
        )
        session.add(
            ToolModel(
                tool_id="file_read",
                name="File Read Tool",
                risk_level="LOW",
            )
        )
        session.commit()

    # Domain service layer wired with SQL repositories
    agent_service = AgentService(
        agent_repository=container.agent_repository,
        enforcement_repository=container.enforcement_repository,
    )
    agent_service.register_agent(
        Agent(
            agent_id="agent-e2e",
            name="E2E Agent",
            owner="security",
            risk_tier=RiskTier.LOW,
            approved_tools=["file_read"],
            status=AgentStatus.ACTIVE,
        )
    )

    tool_service = ToolService(
        tool_repository=container.tool_repository,
    )
    tool_service.register_tool(
        Tool(
            metadata=ToolMetadata(
                identity=ToolIdentity(
                    tool_id="file_read",
                    name="File Read Tool",
                    description="Read files safely",
                ),
                governance=ToolGovernance(risk_level=ToolRiskLevel.LOW),
                capability=ToolCapability(category="filesystem"),
                operational=ToolOperational(),
            )
        )
    )

    policy_engine = PolicyEngine()
    authorization_service = AuthorizationService(
        agent_service=agent_service,
        tool_service=tool_service,
        policy_engine=policy_engine,
    )

    session_service = SessionService(
        session_repository=container.session_repository,
    )

    execution_authority = ExecutionAuthority(
        enforcement_repository=container.enforcement_repository,
    )

    test_tool = MockTestTool(tool_id="file_read")
    descriptor = ToolDescriptor(
        tool_id="file_read",
        enabled=True,
        metadata=test_tool.metadata,
        instance=test_tool,
    )

    executor = DefaultToolExecutor(authority=execution_authority)

    yield {
        "engine": engine,
        "container": container,
        "agent_service": agent_service,
        "session_service": session_service,
        "authorization_service": authorization_service,
        "execution_authority": execution_authority,
        "executor": executor,
        "descriptor": descriptor,
        "test_tool": test_tool,
    }

    dispose_sql_engine(engine)


def test_e2e_case_1_allow_path_exactly_once_execution(sql_pipeline_setup) -> None:
    """Case 1: ALLOW decision produces grant, executes tool once, second attempt fails."""
    env = sql_pipeline_setup
    now = datetime.now(timezone.utc)
    agent_id = "agent-e2e"
    tool_id = "file_read"
    session_id = "sess-e2e-1"
    params = {"path": "safe.txt"}

    # 1. Establish session in SQL session repository via SessionService
    session = env["session_service"].bind_or_validate(session_id, agent_id, now_utc=now)
    assert session.session_id == session_id

    # 2. Evaluate authorization
    auth_result = env["authorization_service"].evaluate(agent_id, tool_id)
    assert auth_result.decision == Decision.ALLOW

    # 3. Record detection horizon event in SQL session repository
    event = env["session_service"].record_event(
        SessionEvent(
            session_id=session_id,
            agent_id=agent_id,
            tool_id=tool_id,
            decision=Decision.ALLOW,
            timestamp=now,
        )
    )
    assert event.sequence_number == 1
    assert event.agent_sequence == 1

    # 4. Issue execution grant via ExecutionAuthority bound to SQL enforcement repository
    binding = ExecutionBinding.from_operation(tool_id, params)
    grant = env["execution_authority"].issue(
        binding,
        auth_result.decision,
        agent_id=agent_id,
        expected_epoch=0,
    )
    assert grant is not None

    # 5. Execute tool via DefaultToolExecutor
    result = env["executor"].execute_descriptor(
        env["descriptor"],
        parameters=params,
        grant=grant,
    )
    assert result == {"status": "success", "params": params}
    assert env["test_tool"].executions == 1

    # 6. Replay attack: second execution attempt with same grant fails closed
    with pytest.raises(ExecutionBindingError) as exc_info:
        env["executor"].execute_descriptor(
            env["descriptor"],
            parameters=params,
            grant=grant,
        )
    assert exc_info.value.reason == ExecutionRefusalReason.CONSUMED
    assert env["test_tool"].executions == 1  # Tool was not run a second time


def test_e2e_case_2_suspended_agent_halts_authorization_no_grant(sql_pipeline_setup) -> None:
    """Case 2: SUSPENDED agent halts authorization, issues no grant, refuses execution."""
    env = sql_pipeline_setup
    agent_id = "agent-e2e"
    tool_id = "file_read"
    params = {"path": "safe.txt"}

    # Contain agent via AgentService through SQL enforcement repository (epoch 0 -> 1, SUSPENDED)
    env["agent_service"].suspend_agent(agent_id, reason="Malicious activity detected")

    # Authorization evaluation must detect suspension from SQL enforcement repository
    auth_result = env["authorization_service"].evaluate(agent_id, tool_id)
    assert auth_result.decision == Decision.DENY
    assert "SUSPENDED" in auth_result.reason

    # ExecutionAuthority refuses grant issuance on non-ALLOW decision
    binding = ExecutionBinding.from_operation(tool_id, params)
    grant = env["execution_authority"].issue(
        binding,
        auth_result.decision,
        agent_id=agent_id,
        expected_epoch=1,
    )
    assert grant is None

    # Executor refuses execution with missing grant
    with pytest.raises(ExecutionBindingError) as exc_info:
        env["executor"].execute_descriptor(
            env["descriptor"],
            parameters=params,
            grant=grant,
        )
    assert exc_info.value.reason == ExecutionRefusalReason.MISSING_GRANT


def test_e2e_case_3_enforcement_interlock_stale_epoch_fails_issuance(sql_pipeline_setup) -> None:
    """Case 3: Concurrently advancing epoch causes ExecutionAuthority to refuse grant issuance."""
    env = sql_pipeline_setup
    agent_id = "agent-e2e"
    tool_id = "file_read"
    params = {"path": "safe.txt"}

    # Authorization evaluates against expected_epoch = 0
    auth_result = env["authorization_service"].evaluate(agent_id, tool_id)
    assert auth_result.decision == Decision.ALLOW

    # Before grant issuance, an enforcement transition commits in SQL (epoch 0 -> 1)
    env["agent_service"].suspend_agent(agent_id, reason="Concurrent containment")

    # Authority attempts to issue grant with stale expected_epoch=0
    # Boundary check against SQL enforcement repository fails closed (returns None)
    binding = ExecutionBinding.from_operation(tool_id, params)
    grant = env["execution_authority"].issue(
        binding,
        auth_result.decision,
        agent_id=agent_id,
        expected_epoch=0,  # Stale epoch (persisted epoch is now 1)
    )
    assert grant is None


def test_e2e_case_4_stale_issued_grant_rejected_after_containment(sql_pipeline_setup) -> None:
    """Case 4: Grant legitimately issued before containment cannot be executed after agent suspension."""
    env = sql_pipeline_setup
    agent_id = "agent-e2e"
    tool_id = "file_read"
    params = {"path": "safe.txt"}

    # Legitimate grant issuance at epoch 0
    binding = ExecutionBinding.from_operation(tool_id, params)
    grant = env["execution_authority"].issue(
        binding,
        Decision.ALLOW,
        agent_id=agent_id,
        expected_epoch=0,
    )
    assert grant is not None

    # Agent containment occurs: ExecutionAuthority closes issuance and revokes outstanding grants
    env["execution_authority"].suspend_issuance(agent_id)

    # Attempt to execute using the previously issued grant
    with pytest.raises(ExecutionBindingError) as exc_info:
        env["executor"].execute_descriptor(
            env["descriptor"],
            parameters=params,
            grant=grant,
        )
    assert exc_info.value.reason == ExecutionRefusalReason.REVOKED
    assert env["test_tool"].executions == 0


def test_e2e_case_5_human_in_the_loop_resumption_exactly_once(sql_pipeline_setup) -> None:
    """Case 5: Human-in-the-loop ExecutionGrant resumption with atomic exactly-once claim."""
    env = sql_pipeline_setup
    now = datetime.now(timezone.utc)
    grant_repo = env["container"].approval_grant_repository
    grant_id = f"grant-{uuid4()}"
    session_id = "sess-e2e-hitl"
    agent_id = "agent-e2e"

    # Establish session in SQL session repository
    env["session_service"].bind_or_validate(session_id, agent_id, now_utc=now)

    # 1. Pipeline emitted REQUIRE_APPROVAL -> create PENDING grant in SQL
    pending_grant = ExecutionGrant(
        grant_id=grant_id,
        session_id=session_id,
        agent_id=agent_id,
        tool_id="file_read",
        execution_parameters={"path": "sensitive.txt"},
        originating_audit_event_id=f"audit-{uuid4()}",
        risk_score=75,
        required_response="REQUIRE_APPROVAL",
        enforcement_epoch=0,
        state=GrantState.PENDING,
        created_at=now,
        expires_at=now,
    )
    grant_repo.create_grant(pending_grant)

    # 2. Operator approves grant
    approved = grant_repo.transition_grant(
        grant_id,
        from_state=GrantState.PENDING,
        to_state=GrantState.APPROVED,
        approved_by="sec-admin",
    )
    assert approved is True

    # 3. Worker 1 claims grant for execution attempt -> succeeds
    claimed_1 = grant_repo.transition_grant(
        grant_id,
        from_state=GrantState.APPROVED,
        to_state=GrantState.CONSUMED,
        consumed_at=now,
    )
    assert claimed_1 is True

    # 4. Worker 2 attempts concurrent claim -> CAS fails, returns False
    claimed_2 = grant_repo.transition_grant(
        grant_id,
        from_state=GrantState.APPROVED,
        to_state=GrantState.CONSUMED,
        consumed_at=now,
    )
    assert claimed_2 is False

    # Stored state is CONSUMED
    stored = grant_repo.get_grant(grant_id)
    assert stored is not None
    assert stored.state == GrantState.CONSUMED
    assert stored.approved_by == "sec-admin"
    assert stored.consumed_at is not None
