"""Reusable contract tests for ApprovalContinuationRepository implementations."""

import abc
from datetime import datetime, timedelta, timezone

import pytest

from app.models.approval_continuation import (
    ApprovalContinuation,
    ContinuationState,
)
from app.repositories.interfaces.approval_continuation_repository import (
    ApprovalContinuationRepository,
    InvalidContinuationTransitionError,
)


class BaseApprovalContinuationRepositoryContractTests(abc.ABC):
    """Abstract contract test suite for any ApprovalContinuationRepository adapter."""

    @abc.abstractmethod
    def create_repository(self) -> ApprovalContinuationRepository:
        """Factory method to construct a fresh, empty repository under test."""
        raise NotImplementedError

    def _sample_grant(
        self,
        grant_id: str = "grant-1",
        agent_id: str = "agent-1",
        state: ContinuationState = ContinuationState.PENDING,
    ) -> ApprovalContinuation:
        now = datetime.now(timezone.utc)
        return ApprovalContinuation(
            grant_id=grant_id,
            session_id="sess-1",
            agent_id=agent_id,
            tool_id="bash",
            tool_version="1.0.0",
            execution_parameters={"cmd": "whoami"},
            originating_audit_event_id="audit-1",
            risk_score=75,
            required_response="REQUIRE_APPROVAL",
            enforcement_epoch=0,
            state=state,
            created_at=now,
            expires_at=now + timedelta(minutes=15),
        )

    def test_create_and_get_continuation(self) -> None:
        repo = self.create_repository()
        grant = self._sample_grant()

        repo.create_continuation(grant)
        retrieved = repo.get_continuation(grant.grant_id)

        assert retrieved is not None
        assert retrieved.grant_id == grant.grant_id
        assert retrieved.tool_id == grant.tool_id
        assert retrieved.state == ContinuationState.PENDING

    def test_get_missing_grant_returns_none(self) -> None:
        repo = self.create_repository()
        assert repo.get_continuation("non-existent-grant") is None

    def test_legal_lifecycle_approved_to_consumed(self) -> None:
        repo = self.create_repository()
        grant = self._sample_grant("grant-legal-1")
        repo.create_continuation(grant)

        # 1. PENDING -> APPROVED requires approved_by
        assert (
            repo.transition_continuation(
                "grant-legal-1",
                from_state=ContinuationState.PENDING,
                to_state=ContinuationState.APPROVED,
                approved_by="operator-alice",
            )
            is True
        )

        approved = repo.get_continuation("grant-legal-1")
        assert approved is not None
        assert approved.state == ContinuationState.APPROVED
        assert approved.approved_by == "operator-alice"
        assert approved.consumed_at is None

        # 2. APPROVED -> CONSUMED requires consumed_at
        now = datetime.now(timezone.utc)
        assert (
            repo.transition_continuation(
                "grant-legal-1",
                from_state=ContinuationState.APPROVED,
                to_state=ContinuationState.CONSUMED,
                consumed_at=now,
            )
            is True
        )

        consumed = repo.get_continuation("grant-legal-1")
        assert consumed is not None
        assert consumed.state == ContinuationState.CONSUMED
        assert consumed.approved_by == "operator-alice"
        assert consumed.consumed_at == now

    def test_legal_rejection_and_expiration(self) -> None:
        repo = self.create_repository()

        # PENDING -> REJECTED
        g_rej = self._sample_grant("grant-rej")
        repo.create_continuation(g_rej)
        assert (
            repo.transition_continuation(
                "grant-rej",
                from_state=ContinuationState.PENDING,
                to_state=ContinuationState.REJECTED,
                approved_by="operator-bob",
            )
            is True
        )
        assert repo.get_continuation("grant-rej").state == ContinuationState.REJECTED

        # PENDING -> EXPIRED
        g_exp = self._sample_grant("grant-exp")
        repo.create_continuation(g_exp)
        assert (
            repo.transition_continuation(
                "grant-exp",
                from_state=ContinuationState.PENDING,
                to_state=ContinuationState.EXPIRED,
            )
            is True
        )
        assert repo.get_continuation("grant-exp").state == ContinuationState.EXPIRED

    def test_illegal_transitions_rejected(self) -> None:
        repo = self.create_repository()
        grant = self._sample_grant("grant-illegal")
        repo.create_continuation(grant)

        # PENDING -> CONSUMED is illegal
        with pytest.raises(InvalidContinuationTransitionError):
            repo.transition_continuation(
                "grant-illegal",
                from_state=ContinuationState.PENDING,
                to_state=ContinuationState.CONSUMED,
                consumed_at=datetime.now(timezone.utc),
            )

        # Transition to APPROVED
        repo.transition_continuation(
            "grant-illegal",
            from_state=ContinuationState.PENDING,
            to_state=ContinuationState.APPROVED,
            approved_by="operator-alice",
        )

        # APPROVED -> REJECTED is illegal
        with pytest.raises(InvalidContinuationTransitionError):
            repo.transition_continuation(
                "grant-illegal",
                from_state=ContinuationState.APPROVED,
                to_state=ContinuationState.REJECTED,
            )

    def test_transition_metadata_invariants(self) -> None:
        repo = self.create_repository()
        grant = self._sample_grant("grant-meta")
        repo.create_continuation(grant)

        # PENDING -> APPROVED without approved_by fails
        with pytest.raises(InvalidContinuationTransitionError):
            repo.transition_continuation(
                "grant-meta",
                from_state=ContinuationState.PENDING,
                to_state=ContinuationState.APPROVED,
                approved_by=None,
            )

        # PENDING -> APPROVED with consumed_at fails
        with pytest.raises(InvalidContinuationTransitionError):
            repo.transition_continuation(
                "grant-meta",
                from_state=ContinuationState.PENDING,
                to_state=ContinuationState.APPROVED,
                approved_by="operator-alice",
                consumed_at=datetime.now(timezone.utc),
            )

        # Successfully approve
        repo.transition_continuation(
            "grant-meta",
            from_state=ContinuationState.PENDING,
            to_state=ContinuationState.APPROVED,
            approved_by="operator-alice",
        )

        # APPROVED -> CONSUMED without consumed_at fails
        with pytest.raises(InvalidContinuationTransitionError):
            repo.transition_continuation(
                "grant-meta",
                from_state=ContinuationState.APPROVED,
                to_state=ContinuationState.CONSUMED,
                consumed_at=None,
            )

    def test_cas_concurrency_conflict_fails_closed(self) -> None:
        repo = self.create_repository()
        grant = self._sample_grant("grant-cas")
        repo.create_continuation(grant)

        # Attempting to consume directly when in PENDING (expecting APPROVED) fails CAS
        now = datetime.now(timezone.utc)
        assert (
            repo.transition_continuation(
                "grant-cas",
                from_state=ContinuationState.APPROVED,
                to_state=ContinuationState.CONSUMED,
                consumed_at=now,
            )
            is False
        )

        # State remains PENDING
        assert repo.get_continuation("grant-cas").state == ContinuationState.PENDING

    def test_list_continuations_filtering(self) -> None:
        repo = self.create_repository()
        g1 = self._sample_grant("g-1", agent_id="a-1")
        g2 = self._sample_grant("g-2", agent_id="a-2")
        repo.create_continuation(g1)
        repo.create_continuation(g2)

        repo.transition_continuation(
            "g-1",
            from_state=ContinuationState.PENDING,
            to_state=ContinuationState.APPROVED,
            approved_by="admin",
        )

        assert len(repo.list_continuations(agent_id="a-1")) == 1
        assert len(repo.list_continuations(state=ContinuationState.APPROVED)) == 1
        assert len(repo.list_continuations(state=ContinuationState.PENDING)) == 1
        assert len(repo.list_continuations(agent_id="unknown")) == 0

    def test_defensive_copy_isolation(self) -> None:
        """Stored and retrieved grants must be isolated defensive copies."""
        repo = self.create_repository()
        grant = self._sample_grant("g-iso-1")
        repo.create_continuation(grant)

        # Invariant: retrieved grant is distinct instance from created grant
        retrieved1 = repo.get_continuation("g-iso-1")
        assert retrieved1 is not None
        assert retrieved1 is not grant

        # Invariant: successive reads produce distinct instances
        retrieved2 = repo.get_continuation("g-iso-1")
        assert retrieved2 is not None
        assert retrieved2 is not retrieved1

        # Verify list collection and item isolation
        grants = repo.list_continuations()
        assert len(grants) == 1
        assert grants[0] is not grant
        assert grants[0] is not retrieved1
        grants.clear()
        assert len(repo.list_continuations()) == 1
