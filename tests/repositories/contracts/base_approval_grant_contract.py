"""Reusable contract tests for ApprovalGrantRepository implementations."""

import abc
from datetime import datetime, timedelta, timezone

import pytest

from app.models.execution_grant import (
    ExecutionGrant,
    GrantState,
)
from app.repositories.interfaces.approval_grant_repository import (
    ApprovalGrantRepository,
    InvalidGrantTransitionError,
)


class BaseApprovalGrantRepositoryContractTests(abc.ABC):
    """Abstract contract test suite for any ApprovalGrantRepository adapter."""

    @abc.abstractmethod
    def create_repository(self) -> ApprovalGrantRepository:
        """Factory method to construct a fresh, empty repository under test."""
        raise NotImplementedError

    def _sample_grant(
        self,
        grant_id: str = "grant-1",
        agent_id: str = "agent-1",
        state: GrantState = GrantState.PENDING,
    ) -> ExecutionGrant:
        now = datetime.now(timezone.utc)
        return ExecutionGrant(
            grant_id=grant_id,
            session_id="sess-1",
            agent_id=agent_id,
            tool_id="bash",
            execution_parameters={"cmd": "whoami"},
            originating_audit_event_id="audit-1",
            risk_score=75,
            required_response="REQUIRE_APPROVAL",
            enforcement_epoch=0,
            state=state,
            created_at=now,
            expires_at=now + timedelta(minutes=15),
        )

    def test_create_and_get_grant(self) -> None:
        repo = self.create_repository()
        grant = self._sample_grant()

        repo.create_grant(grant)
        retrieved = repo.get_grant(grant.grant_id)

        assert retrieved is not None
        assert retrieved.grant_id == grant.grant_id
        assert retrieved.tool_id == grant.tool_id
        assert retrieved.state == GrantState.PENDING

    def test_get_missing_grant_returns_none(self) -> None:
        repo = self.create_repository()
        assert repo.get_grant("non-existent-grant") is None

    def test_legal_lifecycle_approved_to_consumed(self) -> None:
        repo = self.create_repository()
        grant = self._sample_grant("grant-legal-1")
        repo.create_grant(grant)

        # 1. PENDING -> APPROVED requires approved_by
        assert (
            repo.transition_grant(
                "grant-legal-1",
                from_state=GrantState.PENDING,
                to_state=GrantState.APPROVED,
                approved_by="operator-alice",
            )
            is True
        )

        approved = repo.get_grant("grant-legal-1")
        assert approved is not None
        assert approved.state == GrantState.APPROVED
        assert approved.approved_by == "operator-alice"
        assert approved.consumed_at is None

        # 2. APPROVED -> CONSUMED requires consumed_at
        now = datetime.now(timezone.utc)
        assert (
            repo.transition_grant(
                "grant-legal-1",
                from_state=GrantState.APPROVED,
                to_state=GrantState.CONSUMED,
                consumed_at=now,
            )
            is True
        )

        consumed = repo.get_grant("grant-legal-1")
        assert consumed is not None
        assert consumed.state == GrantState.CONSUMED
        assert consumed.approved_by == "operator-alice"
        assert consumed.consumed_at == now

    def test_legal_rejection_and_expiration(self) -> None:
        repo = self.create_repository()

        # PENDING -> REJECTED
        g_rej = self._sample_grant("grant-rej")
        repo.create_grant(g_rej)
        assert (
            repo.transition_grant(
                "grant-rej",
                from_state=GrantState.PENDING,
                to_state=GrantState.REJECTED,
                approved_by="operator-bob",
            )
            is True
        )
        assert repo.get_grant("grant-rej").state == GrantState.REJECTED

        # PENDING -> EXPIRED
        g_exp = self._sample_grant("grant-exp")
        repo.create_grant(g_exp)
        assert (
            repo.transition_grant(
                "grant-exp",
                from_state=GrantState.PENDING,
                to_state=GrantState.EXPIRED,
            )
            is True
        )
        assert repo.get_grant("grant-exp").state == GrantState.EXPIRED

    def test_illegal_transitions_rejected(self) -> None:
        repo = self.create_repository()
        grant = self._sample_grant("grant-illegal")
        repo.create_grant(grant)

        # PENDING -> CONSUMED is illegal
        with pytest.raises(InvalidGrantTransitionError):
            repo.transition_grant(
                "grant-illegal",
                from_state=GrantState.PENDING,
                to_state=GrantState.CONSUMED,
                consumed_at=datetime.now(timezone.utc),
            )

        # Transition to APPROVED
        repo.transition_grant(
            "grant-illegal",
            from_state=GrantState.PENDING,
            to_state=GrantState.APPROVED,
            approved_by="operator-alice",
        )

        # APPROVED -> REJECTED is illegal
        with pytest.raises(InvalidGrantTransitionError):
            repo.transition_grant(
                "grant-illegal",
                from_state=GrantState.APPROVED,
                to_state=GrantState.REJECTED,
            )

    def test_transition_metadata_invariants(self) -> None:
        repo = self.create_repository()
        grant = self._sample_grant("grant-meta")
        repo.create_grant(grant)

        # PENDING -> APPROVED without approved_by fails
        with pytest.raises(InvalidGrantTransitionError):
            repo.transition_grant(
                "grant-meta",
                from_state=GrantState.PENDING,
                to_state=GrantState.APPROVED,
                approved_by=None,
            )

        # PENDING -> APPROVED with consumed_at fails
        with pytest.raises(InvalidGrantTransitionError):
            repo.transition_grant(
                "grant-meta",
                from_state=GrantState.PENDING,
                to_state=GrantState.APPROVED,
                approved_by="operator-alice",
                consumed_at=datetime.now(timezone.utc),
            )

        # Successfully approve
        repo.transition_grant(
            "grant-meta",
            from_state=GrantState.PENDING,
            to_state=GrantState.APPROVED,
            approved_by="operator-alice",
        )

        # APPROVED -> CONSUMED without consumed_at fails
        with pytest.raises(InvalidGrantTransitionError):
            repo.transition_grant(
                "grant-meta",
                from_state=GrantState.APPROVED,
                to_state=GrantState.CONSUMED,
                consumed_at=None,
            )

    def test_cas_concurrency_conflict_fails_closed(self) -> None:
        repo = self.create_repository()
        grant = self._sample_grant("grant-cas")
        repo.create_grant(grant)

        # Attempting to consume directly when in PENDING (expecting APPROVED) fails CAS
        now = datetime.now(timezone.utc)
        assert (
            repo.transition_grant(
                "grant-cas",
                from_state=GrantState.APPROVED,
                to_state=GrantState.CONSUMED,
                consumed_at=now,
            )
            is False
        )

        # State remains PENDING
        assert repo.get_grant("grant-cas").state == GrantState.PENDING

    def test_list_grants_filtering(self) -> None:
        repo = self.create_repository()
        g1 = self._sample_grant("g-1", agent_id="a-1")
        g2 = self._sample_grant("g-2", agent_id="a-2")
        repo.create_grant(g1)
        repo.create_grant(g2)

        repo.transition_grant(
            "g-1",
            from_state=GrantState.PENDING,
            to_state=GrantState.APPROVED,
            approved_by="admin",
        )

        assert len(repo.list_grants(agent_id="a-1")) == 1
        assert len(repo.list_grants(state=GrantState.APPROVED)) == 1
        assert len(repo.list_grants(state=GrantState.PENDING)) == 1
        assert len(repo.list_grants(agent_id="unknown")) == 0

    def test_defensive_copy_isolation(self) -> None:
        """Stored and retrieved grants must be isolated defensive copies."""
        repo = self.create_repository()
        grant = self._sample_grant("g-iso-1")
        repo.create_grant(grant)

        # Invariant: retrieved grant is distinct instance from created grant
        retrieved1 = repo.get_grant("g-iso-1")
        assert retrieved1 is not None
        assert retrieved1 is not grant

        # Invariant: successive reads produce distinct instances
        retrieved2 = repo.get_grant("g-iso-1")
        assert retrieved2 is not None
        assert retrieved2 is not retrieved1

        # Verify list collection and item isolation
        grants = repo.list_grants()
        assert len(grants) == 1
        assert grants[0] is not grant
        assert grants[0] is not retrieved1
        grants.clear()
        assert len(repo.list_grants()) == 1
