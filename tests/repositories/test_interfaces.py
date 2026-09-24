"""Tests for repository protocols and domain persistence interfaces (ADR-030, ADR-031)."""

import inspect
from datetime import datetime, timezone

import pytest

from app.models.agent import Agent, AgentStatus, RiskTier
from app.models.agent_enforcement import (
    AgentEnforcementState,
    EnforcementAction,
    EnforcementTransition,
)
from app.models.audit_event import AuditEvent, Decision
from app.models.execution_grant import ExecutionGrant, GrantState
from app.models.session import Session, TerminalReason, TerminalSessionTombstone
from app.models.session_event import SessionEvent
from app.models.tool import Tool
from app.models.tool_capability import ToolCapability
from app.models.tool_governance import ToolGovernance
from app.models.tool_identity import ToolIdentity
from app.models.tool_metadata import ToolMetadata
from app.models.tool_operational import ToolOperational
from app.models.tool_risk_level import ToolRiskLevel
from app.repositories.interfaces import (
    AgentRepository,
    ApprovalGrantRepository,
    AuditEvidenceRepository,
    EnforcementStateRepository,
    InvalidGrantTransitionError,
    SessionRepository,
    ToolRepository,
)


class MockAgentRepository:
    """In-memory stub verifying AgentRepository protocol compliance."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def get(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def save(self, agent: Agent) -> None:
        self._agents[agent.agent_id] = agent

    def list(self) -> list[Agent]:
        return list(self._agents.values())


class MockToolRepository:
    """In-memory stub verifying ToolRepository protocol compliance."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def get(self, tool_id: str) -> Tool | None:
        return self._tools.get(tool_id)

    def save(self, tool: Tool) -> None:
        self._tools[tool.tool_id] = tool

    def list(self) -> list[Tool]:
        return list(self._tools.values())


class MockAuditEvidenceRepository:
    """In-memory stub verifying AuditEvidenceRepository protocol compliance."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)

    def get(self, event_id: str) -> AuditEvent | None:
        for ev in self._events:
            if ev.event_id == event_id:
                return ev
        return None

    def query(
        self,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        res = self._events
        if session_id is not None:
            res = [e for e in res if e.session_id == session_id]
        if agent_id is not None:
            res = [e for e in res if e.agent_id == agent_id]
        return res[offset : offset + limit]


class MockEnforcementStateRepository:
    """In-memory stub verifying EnforcementStateRepository protocol compliance."""

    def __init__(self) -> None:
        self._state: dict[str, AgentEnforcementState] = {}
        self._transitions: list[EnforcementTransition] = []
        self._epochs: dict[str, int] = {}

    def get_state(self, agent_id: str) -> AgentEnforcementState | None:
        return self._state.get(agent_id)

    def record_transition(
        self,
        transition: EnforcementTransition,
        new_state: AgentEnforcementState,
        *,
        expected_epoch: int,
    ) -> bool:
        agent_id = transition.agent_id
        current_epoch = self._epochs.get(agent_id, 0)
        if current_epoch != expected_epoch:
            return False
        self._state[agent_id] = new_state
        self._transitions.append(transition)
        self._epochs[agent_id] = expected_epoch + 1
        return True

    def list_transitions(
        self,
        agent_id: str | None = None,
    ) -> list[EnforcementTransition]:
        if agent_id is None:
            return list(self._transitions)
        return [t for t in self._transitions if t.agent_id == agent_id]

    def get_epoch(
        self,
        agent_id: str,
        *,
        as_of: datetime,
    ) -> int:
        return sum(
            1
            for t in self._transitions
            if t.agent_id == agent_id
            and t.action == EnforcementAction.REINSTATE
            and t.occurred_at <= as_of
        )


class MockSessionRepository:
    """In-memory stub verifying SessionRepository protocol compliance."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._tombstones: dict[str, TerminalSessionTombstone] = {}
        self._events: list[SessionEvent] = []

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def save_session(self, session: Session) -> None:
        self._sessions[session.session_id] = session

    def list_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    def get_tombstone(self, session_id: str) -> TerminalSessionTombstone | None:
        return self._tombstones.get(session_id)

    def save_tombstone(self, tombstone: TerminalSessionTombstone) -> None:
        self._tombstones[tombstone.session_id] = tombstone

    def terminalize_session(
        self,
        session_id: str,
        tombstone: TerminalSessionTombstone,
    ) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        self._tombstones[session_id] = tombstone
        return True

    def record_event(self, event: SessionEvent) -> None:
        self._events.append(event)

    def list_events(self, session_id: str) -> list[SessionEvent]:
        matching = [e for e in self._events if e.session_id == session_id]
        return sorted(matching, key=lambda e: (e.timestamp, e.sequence_number or 0))

    def prune_events(self, *, cutoff: datetime) -> int:
        initial = len(self._events)
        self._events = [e for e in self._events if e.timestamp >= cutoff]
        return initial - len(self._events)


class MockApprovalGrantRepository:
    """In-memory stub verifying ApprovalGrantRepository protocol compliance."""

    def __init__(self) -> None:
        self._grants: dict[str, ExecutionGrant] = {}

    def create_grant(self, grant: ExecutionGrant) -> None:
        self._grants[grant.grant_id] = grant

    def get_grant(self, grant_id: str) -> ExecutionGrant | None:
        return self._grants.get(grant_id)

    def transition_grant(
        self,
        grant_id: str,
        *,
        from_state: GrantState,
        to_state: GrantState,
        consumed_at: datetime | None = None,
        approved_by: str | None = None,
    ) -> bool:
        allowed = {
            (GrantState.PENDING, GrantState.APPROVED),
            (GrantState.PENDING, GrantState.REJECTED),
            (GrantState.PENDING, GrantState.EXPIRED),
            (GrantState.APPROVED, GrantState.CONSUMED),
        }
        if (from_state, to_state) not in allowed:
            raise InvalidGrantTransitionError(
                f"Transition from {from_state} to {to_state} is illegal under ADR-031"
            )

        grant = self._grants.get(grant_id)
        if grant is None or grant.state != from_state:
            return False

        updated = grant.model_copy(
            update={
                "state": to_state,
                "approved_by": approved_by or grant.approved_by,
                "consumed_at": consumed_at or grant.consumed_at,
            }
        )
        self._grants[grant_id] = updated
        return True

    def list_grants(
        self,
        *,
        agent_id: str | None = None,
        state: GrantState | None = None,
    ) -> list[ExecutionGrant]:
        res = list(self._grants.values())
        if agent_id is not None:
            res = [g for g in res if g.agent_id == agent_id]
        if state is not None:
            res = [g for g in res if g.state == state]
        return res


def _dummy_tool() -> Tool:
    return Tool(
        metadata=ToolMetadata(
            identity=ToolIdentity(tool_id="test_tool", name="Test Tool", description="Test Tool Desc"),
            governance=ToolGovernance(risk_level=ToolRiskLevel.LOW),
            capability=ToolCapability(category="filesystem"),
            operational=ToolOperational(),
        )
    )


class TestRepositoryProtocolConformance:
    """Verify structural typing and method expectations of all Phase 1 repository protocols."""

    def test_agent_repository_methods(self) -> None:
        repo: AgentRepository = MockAgentRepository()
        agent = Agent(
            agent_id="test-agent-1",
            name="Test Agent",
            owner="admin",
            status=AgentStatus.ACTIVE,
            risk_tier=RiskTier.LOW,
        )
        repo.save(agent)
        assert repo.get("test-agent-1") == agent
        assert repo.list() == [agent]
        assert repo.get("unknown") is None

    def test_tool_repository_methods(self) -> None:
        repo: ToolRepository = MockToolRepository()
        tool = _dummy_tool()
        repo.save(tool)
        assert repo.get("test_tool") == tool
        assert repo.list() == [tool]
        assert repo.get("unknown") is None

    def test_audit_evidence_repository_is_append_only(self) -> None:
        repo: AuditEvidenceRepository = MockAuditEvidenceRepository()
        now = datetime.now(timezone.utc)
        ev = AuditEvent(
            event_id="audit-1",
            session_id="session-1",
            agent_id="agent-1",
            tool_id="test_tool",
            decision=Decision.ALLOW,
            timestamp=now,
        )
        repo.append(ev)
        assert repo.get("audit-1") == ev
        assert len(repo.query(session_id="session-1")) == 1
        assert len(repo.query(agent_id="other")) == 0

        # Invariant: verify no delete or update methods exist on protocol
        assert not hasattr(AuditEvidenceRepository, "delete")
        assert not hasattr(AuditEvidenceRepository, "update")
        assert not hasattr(AuditEvidenceRepository, "count")

    def test_enforcement_state_repository_requires_mandatory_expected_epoch(self) -> None:
        repo: EnforcementStateRepository = MockEnforcementStateRepository()
        now = datetime.now(timezone.utc)
        agent_id = "agent-cas-1"

        state_active = AgentEnforcementState(agent_id=agent_id)
        trans1 = EnforcementTransition(
            transition_id="t-1",
            agent_id=agent_id,
            action=EnforcementAction.SUSPEND,
            actor="runtime",
            reason="Violation",
            previous_status=AgentStatus.ACTIVE,
            new_status=AgentStatus.SUSPENDED,
            occurred_at=now,
        )

        # Expected epoch is 0 on fresh agent
        assert repo.record_transition(trans1, state_active, expected_epoch=0) is True

        # Stale CAS attempt (expecting 0 when epoch is now 1) must fail closed
        trans2 = EnforcementTransition(
            transition_id="t-2",
            agent_id=agent_id,
            action=EnforcementAction.REINSTATE,
            actor="sec-ops",
            reason="Remediated",
            previous_status=AgentStatus.SUSPENDED,
            new_status=AgentStatus.ACTIVE,
            occurred_at=now,
        )
        assert repo.record_transition(trans2, state_active, expected_epoch=0) is False

        # Correct expected epoch commits successfully
        assert repo.record_transition(trans2, state_active, expected_epoch=1) is True
        assert len(repo.list_transitions(agent_id=agent_id)) == 2
        assert repo.get_epoch(agent_id, as_of=now) == 1

        # Protocol signature inspection: expected_epoch MUST be a mandatory keyword-only argument
        sig = inspect.signature(EnforcementStateRepository.record_transition)
        param = sig.parameters["expected_epoch"]
        assert param.kind == inspect.Parameter.KEYWORD_ONLY
        assert param.default is inspect.Parameter.empty

    def test_session_repository_has_atomic_terminalization_and_no_deletion(self) -> None:
        repo: SessionRepository = MockSessionRepository()
        now = datetime.now(timezone.utc)
        session_id = "sess-lifecycle-1"

        # Invariant: delete_session must NOT exist
        assert not hasattr(SessionRepository, "delete_session")
        assert not hasattr(MockSessionRepository, "delete_session")

        session = Session(
            session_id=session_id,
            agent_id="agent-1",
            started_at=now,
            last_activity_at=now,
        )
        repo.save_session(session)
        assert repo.get_session(session_id) == session

        tombstone = TerminalSessionTombstone(
            session_id=session_id,
            agent_id="agent-1",
            terminated_at=now,
            terminal_reason=TerminalReason.EXPLICIT_END,
        )

        # Atomic terminalization removes active session and writes tombstone
        assert repo.terminalize_session(session_id, tombstone) is True
        assert repo.get_session(session_id) is None
        assert repo.get_tombstone(session_id) == tombstone

        # Second terminalization attempt returns False
        assert repo.terminalize_session(session_id, tombstone) is False

    def test_approval_grant_repository_state_transitions(self) -> None:
        repo: ApprovalGrantRepository = MockApprovalGrantRepository()
        now = datetime.now(timezone.utc)
        grant = ExecutionGrant(
            grant_id="grant-flow-1",
            session_id="sess-1",
            agent_id="agent-1",
            tool_id="bash",
            execution_parameters={"cmd": "ls"},
            originating_audit_event_id="audit-1",
            risk_score=80,
            required_response="REQUIRE_APPROVAL",
            enforcement_epoch=0,
            state=GrantState.PENDING,
            created_at=now,
            expires_at=now,
        )
        repo.create_grant(grant)

        # Illegal transition: PENDING -> CONSUMED must raise InvalidGrantTransitionError
        with pytest.raises(InvalidGrantTransitionError):
            repo.transition_grant(
                "grant-flow-1",
                from_state=GrantState.PENDING,
                to_state=GrantState.CONSUMED,
            )

        # Legal transition: PENDING -> APPROVED
        assert (
            repo.transition_grant(
                "grant-flow-1",
                from_state=GrantState.PENDING,
                to_state=GrantState.APPROVED,
                approved_by="alice",
            )
            is True
        )

        # Legal transition: APPROVED -> CONSUMED (with consumed_at timestamp)
        consumed_time = datetime.now(timezone.utc)
        assert (
            repo.transition_grant(
                "grant-flow-1",
                from_state=GrantState.APPROVED,
                to_state=GrantState.CONSUMED,
                consumed_at=consumed_time,
            )
            is True
        )

        retrieved = repo.get_grant("grant-flow-1")
        assert retrieved is not None
        assert retrieved.state == GrantState.CONSUMED
        assert retrieved.approved_by == "alice"
        assert retrieved.consumed_at == consumed_time

        # Attempting second consumption (APPROVED -> CONSUMED) fails CAS
        assert (
            repo.transition_grant(
                "grant-flow-1",
                from_state=GrantState.APPROVED,
                to_state=GrantState.CONSUMED,
                consumed_at=consumed_time,
            )
            is False
        )
