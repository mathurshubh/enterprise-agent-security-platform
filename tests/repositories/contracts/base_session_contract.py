"""Reusable contract tests for SessionRepository implementations."""

import abc
from datetime import datetime, timezone

from app.models.audit_event import Decision
from app.models.session import Session, TerminalReason, TerminalSessionTombstone
from app.models.session_event import SessionEvent
from app.repositories.interfaces.session_repository import SessionRepository


class BaseSessionRepositoryContractTests(abc.ABC):
    """Abstract contract test suite for any SessionRepository adapter."""

    @abc.abstractmethod
    def create_repository(self) -> SessionRepository:
        """Factory method to construct a fresh, empty repository under test."""
        raise NotImplementedError

    def _sample_session(
        self, session_id: str = "sess-1", agent_id: str = "agent-1"
    ) -> Session:
        now = datetime.now(timezone.utc)
        return Session(
            session_id=session_id,
            agent_id=agent_id,
            started_at=now,
            last_activity_at=now,
        )

    def _sample_tombstone(
        self, session_id: str = "sess-1", agent_id: str = "agent-1"
    ) -> TerminalSessionTombstone:
        return TerminalSessionTombstone(
            session_id=session_id,
            agent_id=agent_id,
            terminated_at=datetime.now(timezone.utc),
            terminal_reason=TerminalReason.EXPLICIT_END,
        )

    def _sample_event(
        self,
        session_id: str = "sess-1",
        sequence_number: int = 1,
        timestamp: datetime | None = None,
    ) -> SessionEvent:
        return SessionEvent(
            session_id=session_id,
            agent_id="agent-1",
            tool_id="file_read",
            decision=Decision.ALLOW,
            timestamp=timestamp or datetime.now(timezone.utc),
            sequence_number=sequence_number,
        )

    def test_save_and_get_session(self) -> None:
        repo = self.create_repository()
        session = self._sample_session()

        repo.save_session(session)
        retrieved = repo.get_session(session.session_id)

        assert retrieved is not None
        assert retrieved.session_id == session.session_id
        assert retrieved.agent_id == session.agent_id

    def test_get_missing_session_returns_none(self) -> None:
        repo = self.create_repository()
        assert repo.get_session("non-existent-session") is None
        assert repo.get_tombstone("non-existent-session") is None

    def test_atomic_terminalization_success_invariants(self) -> None:
        """Active session transition to tombstone must be strictly atomic."""
        repo = self.create_repository()
        session_id = "sess-term-1"
        session = self._sample_session(session_id)
        repo.save_session(session)

        tombstone = self._sample_tombstone(session_id)
        assert repo.terminalize_session(session_id, tombstone) is True

        # Invariant: session must NOT exist in active sessions
        assert repo.get_session(session_id) is None

        # Invariant: tombstone MUST exist
        assert repo.get_tombstone(session_id) is not None
        assert repo.get_tombstone(session_id) == tombstone

    def test_terminalization_failure_leaves_collections_unmodified(self) -> None:
        """Failed terminalization must not modify active sessions or tombstones."""
        repo = self.create_repository()
        session_id = "sess-term-2"
        tombstone = self._sample_tombstone(session_id)

        # Case 1: Session not active, no tombstone -> False, collections empty
        assert repo.terminalize_session(session_id, tombstone) is False
        assert repo.get_session(session_id) is None
        assert repo.get_tombstone(session_id) is None

        # Case 2: Session active, successfully terminalized
        session = self._sample_session(session_id)
        repo.save_session(session)
        assert repo.terminalize_session(session_id, tombstone) is True

        # Case 3: Session already terminal -> second attempt returns False, tombstone preserved
        second_tombstone = TerminalSessionTombstone(
            session_id=session_id,
            agent_id="agent-1",
            terminated_at=datetime.now(timezone.utc),
            terminal_reason=TerminalReason.IDLE_TIMEOUT,
        )
        assert repo.terminalize_session(session_id, second_tombstone) is False
        assert repo.get_tombstone(session_id) == tombstone  # unmodified

    def test_deterministic_ordering_with_timestamp_ties(self) -> None:
        """Events sharing equal timestamps must deterministically sort by (timestamp, sequence_number)."""
        repo = self.create_repository()
        same_time = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
        session_id = "sess-order-1"

        # Record out of sequence order
        repo.record_event(
            self._sample_event(session_id, sequence_number=3, timestamp=same_time)
        )
        repo.record_event(
            self._sample_event(session_id, sequence_number=1, timestamp=same_time)
        )
        repo.record_event(
            self._sample_event(session_id, sequence_number=2, timestamp=same_time)
        )

        events = repo.list_events(session_id)
        sequences = [e.sequence_number for e in events]
        assert sequences == [1, 2, 3]

    def test_prune_events(self) -> None:
        repo = self.create_repository()
        session_id = "sess-prune"
        t1 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 24, 10, 5, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 24, 10, 10, 0, tzinfo=timezone.utc)

        repo.record_event(
            self._sample_event(session_id, sequence_number=1, timestamp=t1)
        )
        repo.record_event(
            self._sample_event(session_id, sequence_number=2, timestamp=t2)
        )
        repo.record_event(
            self._sample_event(session_id, sequence_number=3, timestamp=t3)
        )

        # Cutoff at 10:05 -> evicts t1 (older than cutoff)
        evicted = repo.prune_events(cutoff=t2)
        assert evicted == 1

        remaining = repo.list_events(session_id)
        assert [e.sequence_number for e in remaining] == [2, 3]

    def test_no_arbitrary_deletion_method(self) -> None:
        assert not hasattr(SessionRepository, "delete_session")

    def test_save_defensive_copy_isolation(self) -> None:
        """Mutating source session after save must not affect repository state."""
        repo = self.create_repository()
        session = self._sample_session("sess-iso-1")
        repo.save_session(session)

        # Mutate local object
        session.agent_id = "tampered-agent"

        retrieved = repo.get_session("sess-iso-1")
        assert retrieved is not None
        assert retrieved.agent_id != "tampered-agent"

    def test_get_defensive_copy_isolation(self) -> None:
        """Mutating retrieved session must not affect repository state."""
        repo = self.create_repository()
        session = self._sample_session("sess-iso-2")
        repo.save_session(session)

        retrieved1 = repo.get_session("sess-iso-2")
        assert retrieved1 is not None
        retrieved1.agent_id = "tampered-agent"

        retrieved2 = repo.get_session("sess-iso-2")
        assert retrieved2 is not None
        assert retrieved2.agent_id != "tampered-agent"

    def test_list_collection_isolation(self) -> None:
        """Mutating the list returned by list_sessions() must not affect subsequent queries."""
        repo = self.create_repository()
        session = self._sample_session("sess-iso-3")
        repo.save_session(session)

        sessions = repo.list_sessions()
        sessions.clear()
        assert len(repo.list_sessions()) == 1
