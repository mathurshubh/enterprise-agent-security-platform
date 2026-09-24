"""Reusable contract tests for SessionRepository implementations."""

import abc
from datetime import datetime, timezone

import pytest

from app.models.audit_event import Decision
from app.models.session import (
    Session,
    SessionAlreadyExistsError,
    SessionBindingError,
    SessionNotFoundError,
    SessionTerminalError,
    TerminalReason,
    TerminalSessionTombstone,
)
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
        sequence_number: int = 0,
        timestamp: datetime | None = None,
        agent_id: str = "agent-1",
    ) -> SessionEvent:
        return SessionEvent(
            session_id=session_id,
            agent_id=agent_id,
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

    def test_bind_or_create_session_new(self) -> None:
        repo = self.create_repository()
        now = datetime.now(timezone.utc)
        session = repo.bind_or_create_session("sess-new", "agent-1", now=now)
        assert session.session_id == "sess-new"
        assert session.agent_id == "agent-1"
        assert session.started_at == now
        assert session.last_activity_at == now
        assert repo.get_session("sess-new") == session

    def test_bind_or_create_session_existing_same_agent(self) -> None:
        repo = self.create_repository()
        t1 = datetime(2026, 9, 25, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 25, 10, 5, 0, tzinfo=timezone.utc)
        s1 = repo.bind_or_create_session("sess-existing", "agent-1", now=t1)
        assert s1.last_activity_at == t1

        s2 = repo.bind_or_create_session("sess-existing", "agent-1", now=t2)
        assert s2.last_activity_at == t2
        assert s2.started_at == t1
        assert s2.agent_id == "agent-1"

    def test_bind_or_create_session_conflict_different_agent(self) -> None:
        repo = self.create_repository()
        now = datetime.now(timezone.utc)
        repo.bind_or_create_session("sess-conflict", "agent-1", now=now)
        with pytest.raises(SessionBindingError) as exc_info:
            repo.bind_or_create_session("sess-conflict", "agent-2", now=now)
        assert exc_info.value.session_id == "sess-conflict"
        assert exc_info.value.owner_agent_id == "agent-1"
        assert exc_info.value.requested_agent_id == "agent-2"

    def test_bind_or_create_session_terminal_conflict(self) -> None:
        repo = self.create_repository()
        now = datetime.now(timezone.utc)
        repo.bind_or_create_session("sess-term", "agent-1", now=now)
        tombstone = self._sample_tombstone("sess-term", "agent-1")
        assert repo.terminalize_session("sess-term", tombstone) is True

        with pytest.raises(SessionTerminalError) as exc_info:
            repo.bind_or_create_session("sess-term", "agent-1", now=now)
        assert exc_info.value.session_id == "sess-term"
        assert exc_info.value.owner_agent_id == "agent-1"

    def test_create_session_already_exists(self) -> None:
        repo = self.create_repository()
        session = self._sample_session("sess-dup")
        repo.create_session(session)
        with pytest.raises(SessionAlreadyExistsError):
            repo.create_session(session)

    def test_create_session_terminal_conflict(self) -> None:
        repo = self.create_repository()
        session = self._sample_session("sess-term-create")
        repo.create_session(session)
        tombstone = self._sample_tombstone("sess-term-create")
        assert repo.terminalize_session("sess-term-create", tombstone) is True

        with pytest.raises(SessionTerminalError):
            repo.create_session(session)

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

    def test_record_event_requires_existing_session(self) -> None:
        repo = self.create_repository()
        event = self._sample_event("nonexistent-session")
        with pytest.raises(SessionNotFoundError):
            repo.record_event(event)

    def test_record_event_on_terminal_session_fails_closed(self) -> None:
        repo = self.create_repository()
        session_id = "sess-term-evt"
        repo.save_session(self._sample_session(session_id))
        repo.terminalize_session(session_id, self._sample_tombstone(session_id))

        with pytest.raises(SessionTerminalError):
            repo.record_event(self._sample_event(session_id))

    def test_record_event_wrong_agent_fails_closed(self) -> None:
        repo = self.create_repository()
        session_id = "sess-wrong-agent"
        repo.save_session(self._sample_session(session_id, agent_id="agent-1"))

        event = SessionEvent(
            session_id=session_id,
            agent_id="agent-2",
            tool_id="file_read",
            decision=Decision.ALLOW,
        )
        with pytest.raises(SessionBindingError):
            repo.record_event(event)

    def test_record_event_rejects_caller_supplied_sequence(self) -> None:
        repo = self.create_repository()
        session_id = "sess-reject-seq"
        repo.save_session(self._sample_session(session_id))

        event = self._sample_event(session_id, sequence_number=42)
        with pytest.raises(ValueError):
            repo.record_event(event)

    def test_record_event_strictly_increasing_sequence_allocation(self) -> None:
        repo = self.create_repository()
        session_id = "sess-seq"
        repo.save_session(self._sample_session(session_id))

        e1 = repo.record_event(self._sample_event(session_id))
        e2 = repo.record_event(self._sample_event(session_id))
        e3 = repo.record_event(self._sample_event(session_id))

        assert e1.sequence_number == 1
        assert e2.sequence_number == 2
        assert e3.sequence_number == 3
        assert e1.sequence_number < e2.sequence_number < e3.sequence_number

    def test_deterministic_ordering_with_timestamp_ties(self) -> None:
        """Events sharing equal timestamps must deterministically sort by (timestamp, sequence_number)."""
        repo = self.create_repository()
        same_time = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
        session_id = "sess-order-1"
        repo.save_session(self._sample_session(session_id))

        # Record events sequentially sharing equal timestamp
        e1 = repo.record_event(self._sample_event(session_id, timestamp=same_time))
        e2 = repo.record_event(self._sample_event(session_id, timestamp=same_time))
        e3 = repo.record_event(self._sample_event(session_id, timestamp=same_time))

        assert e1.sequence_number == 1
        assert e2.sequence_number == 2
        assert e3.sequence_number == 3

        events = repo.list_events(session_id)
        sequences = [e.sequence_number for e in events]
        assert sequences == [1, 2, 3]

    def test_prune_events(self) -> None:
        repo = self.create_repository()
        session_id = "sess-prune"
        repo.save_session(self._sample_session(session_id))
        t1 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 24, 10, 5, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 9, 24, 10, 10, 0, tzinfo=timezone.utc)

        repo.record_event(self._sample_event(session_id, timestamp=t1))
        repo.record_event(self._sample_event(session_id, timestamp=t2))
        repo.record_event(self._sample_event(session_id, timestamp=t3))

        # Cutoff at 10:05 -> evicts t1 (older than cutoff)
        evicted = repo.prune_events(cutoff=t2)
        assert evicted == 1

        remaining = repo.list_events(session_id)
        assert [e.sequence_number for e in remaining] == [2, 3]

    def test_pruning_preserves_sequence_counter_and_survivors(self) -> None:
        repo = self.create_repository()
        session_id = "sess-prune-seq"
        repo.save_session(self._sample_session(session_id))
        t1 = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 24, 10, 5, 0, tzinfo=timezone.utc)

        e1 = repo.record_event(self._sample_event(session_id, timestamp=t1))
        e2 = repo.record_event(self._sample_event(session_id, timestamp=t2))
        assert e1.sequence_number == 1
        assert e2.sequence_number == 2

        # Evict everything
        cutoff_future = datetime(2026, 9, 24, 11, 0, 0, tzinfo=timezone.utc)
        evicted = repo.prune_events(cutoff=cutoff_future)
        assert evicted == 2
        assert repo.list_events(session_id) == []

        # Next recorded event MUST receive sequence 3, not reset to 1
        t3 = datetime(2026, 9, 24, 11, 5, 0, tzinfo=timezone.utc)
        e3 = repo.record_event(self._sample_event(session_id, timestamp=t3))
        assert e3.sequence_number == 3

    def test_concurrent_session_binding(self) -> None:
        import threading

        repo = self.create_repository()
        session_id = "sess-concurrent-bind"
        agent_id = "agent-1"
        now = datetime.now(timezone.utc)

        results = []
        errors = []

        def worker():
            try:
                s = repo.bind_or_create_session(session_id, agent_id, now=now)
                results.append(s)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
        assert all(s.session_id == session_id for s in results)
        assert len(repo.list_sessions()) == 1

    def test_concurrent_event_recording_allocates_unique_sequences(self) -> None:
        import threading

        repo = self.create_repository()
        session_id = "sess-concurrent-events"
        repo.save_session(self._sample_session(session_id))

        recorded_events = []
        errors = []

        def worker():
            try:
                e = repo.record_event(self._sample_event(session_id))
                recorded_events.append(e)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(recorded_events) == 20
        sequences = [e.sequence_number for e in recorded_events]
        assert len(set(sequences)) == 20
        assert sorted(sequences) == list(range(1, 21))

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

    def test_update_event_final_decision_success(self) -> None:
        repo = self.create_repository()
        session_id = "sess-update-fd"
        repo.save_session(self._sample_session(session_id))
        ev = repo.record_event(self._sample_event(session_id))
        assert ev.final_decision is None

        repo.update_event_final_decision(
            session_id=session_id,
            sequence_number=ev.sequence_number,
            final_decision=Decision.APPROVAL_REQUIRED,
        )

        events = repo.list_events(session_id)
        assert len(events) == 1
        assert events[0].final_decision == Decision.APPROVAL_REQUIRED

    def test_update_event_final_decision_preserves_all_historical_fields(self) -> None:
        """Historical fields (sequence, timestamp, agent, session, auth decision, tool) must be immutable."""
        repo = self.create_repository()
        session_id = "sess-update-immut"
        agent_id = "agent-immut"
        timestamp = datetime(2026, 9, 24, 15, 30, 0, tzinfo=timezone.utc)
        repo.save_session(self._sample_session(session_id, agent_id=agent_id))

        event = SessionEvent(
            session_id=session_id,
            agent_id=agent_id,
            tool_id="shell_exec",
            decision=Decision.ALLOW,
            timestamp=timestamp,
        )
        recorded = repo.record_event(event)

        repo.update_event_final_decision(
            session_id=session_id,
            sequence_number=recorded.sequence_number,
            final_decision=Decision.DENY,
        )

        persisted = repo.list_events(session_id)[0]
        assert persisted.final_decision == Decision.DENY
        # Verify strict historical field immutability
        assert persisted.sequence_number == recorded.sequence_number
        assert persisted.timestamp == timestamp
        assert persisted.agent_id == agent_id
        assert persisted.session_id == session_id
        assert persisted.decision == Decision.ALLOW  # original auth decision preserved
        assert persisted.tool_id == "shell_exec"

    def test_update_event_final_decision_rejects_second_conflicting_update(
        self,
    ) -> None:
        """A finalized event cannot transition to a different decision (e.g. APPROVAL_REQUIRED -> DENY)."""
        repo = self.create_repository()
        session_id = "sess-reject-second"
        repo.save_session(self._sample_session(session_id))
        ev = repo.record_event(self._sample_event(session_id))

        # First finalization
        repo.update_event_final_decision(
            session_id=session_id,
            sequence_number=ev.sequence_number,
            final_decision=Decision.APPROVAL_REQUIRED,
        )

        # Second conflicting finalization must be deterministically rejected
        with pytest.raises(ValueError, match="already finalized"):
            repo.update_event_final_decision(
                session_id=session_id,
                sequence_number=ev.sequence_number,
                final_decision=Decision.DENY,
            )

        # State must remain the first finalized decision
        events = repo.list_events(session_id)
        assert events[0].final_decision == Decision.APPROVAL_REQUIRED

    def test_update_event_final_decision_idempotent_for_identical_value(self) -> None:
        """Finalizing an event with the exact same final_decision is an idempotent no-op."""
        repo = self.create_repository()
        session_id = "sess-idempotent-fd"
        repo.save_session(self._sample_session(session_id))
        ev = repo.record_event(self._sample_event(session_id))

        repo.update_event_final_decision(
            session_id=session_id,
            sequence_number=ev.sequence_number,
            final_decision=Decision.ALLOW,
        )
        # Identical re-finalization succeeds idempotently
        repo.update_event_final_decision(
            session_id=session_id,
            sequence_number=ev.sequence_number,
            final_decision=Decision.ALLOW,
        )

        events = repo.list_events(session_id)
        assert events[0].final_decision == Decision.ALLOW

    def test_update_event_final_decision_wrong_session_isolation(self) -> None:
        """Updating an event in one session must not mutate or touch another session's evidence."""
        repo = self.create_repository()
        sess_a = "sess-iso-a"
        sess_b = "sess-iso-b"
        repo.save_session(self._sample_session(sess_a, agent_id="agent-a"))
        repo.save_session(self._sample_session(sess_b, agent_id="agent-b"))

        ev_a = repo.record_event(self._sample_event(sess_a, agent_id="agent-a"))
        ev_b = repo.record_event(self._sample_event(sess_b, agent_id="agent-b"))
        assert ev_a.sequence_number == 1
        assert ev_b.sequence_number == 1

        # Update session A only
        repo.update_event_final_decision(
            session_id=sess_a,
            sequence_number=ev_a.sequence_number,
            final_decision=Decision.DENY,
        )

        events_a = repo.list_events(sess_a)
        events_b = repo.list_events(sess_b)
        assert events_a[0].final_decision == Decision.DENY
        assert events_b[0].final_decision is None  # Session B's event must remain unset

    def test_update_event_final_decision_session_not_found(self) -> None:
        repo = self.create_repository()
        with pytest.raises(SessionNotFoundError):
            repo.update_event_final_decision(
                session_id="nonexistent-sess",
                sequence_number=1,
                final_decision=Decision.DENY,
            )

    def test_update_event_final_decision_session_terminal(self) -> None:
        repo = self.create_repository()
        session_id = "sess-term-update"
        repo.save_session(self._sample_session(session_id))
        repo.terminalize_session(session_id, self._sample_tombstone(session_id))

        with pytest.raises(SessionTerminalError):
            repo.update_event_final_decision(
                session_id=session_id,
                sequence_number=1,
                final_decision=Decision.DENY,
            )

    def test_update_event_final_decision_sequence_not_found(self) -> None:
        repo = self.create_repository()
        session_id = "sess-seq-not-found"
        repo.save_session(self._sample_session(session_id))
        repo.record_event(self._sample_event(session_id))

        with pytest.raises(ValueError):
            repo.update_event_final_decision(
                session_id=session_id,
                sequence_number=999,
                final_decision=Decision.DENY,
            )
