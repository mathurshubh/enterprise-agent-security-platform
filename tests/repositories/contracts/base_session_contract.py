"""Reusable contract tests for SessionRepository implementations."""

import abc
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

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
from app.models.session_event import (
    AggregationScope,
    HorizonQuery,
    SessionEvent,
)
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

    # -------------------------------------------------------------------------
    # Plane 2: Detection Horizon 18-Test Contract Matrix
    # -------------------------------------------------------------------------

    def test_dual_sequence_allocation_across_sessions(self) -> None:
        """Dual Monotonic Positioning: sequence_number is session-local; agent_sequence is agent-scoped."""
        repo = self.create_repository()
        repo.save_session(self._sample_session("sess-a1", agent_id="agent-a"))
        repo.save_session(self._sample_session("sess-a2", agent_id="agent-a"))
        repo.save_session(self._sample_session("sess-b1", agent_id="agent-b"))

        # Session 1 for Agent A
        e1 = repo.record_event(self._sample_event("sess-a1", agent_id="agent-a"))
        e2 = repo.record_event(self._sample_event("sess-a1", agent_id="agent-a"))
        assert e1.sequence_number == 1
        assert e1.agent_sequence == 1
        assert e2.sequence_number == 2
        assert e2.agent_sequence == 2

        # Session 2 for Agent A: sequence_number resets to 1, agent_sequence increments monotonically
        e3 = repo.record_event(self._sample_event("sess-a2", agent_id="agent-a"))
        assert e3.sequence_number == 1
        assert e3.agent_sequence == 3

        # Session 1 for Agent B: separate agent identity, agent_sequence starts at 1
        e4 = repo.record_event(self._sample_event("sess-b1", agent_id="agent-b"))
        assert e4.sequence_number == 1
        assert e4.agent_sequence == 1

    def test_record_event_rejects_caller_supplied_sequences(self) -> None:
        """Callers cannot supply non-zero sequence_number or agent_sequence."""
        repo = self.create_repository()
        session_id = "sess-reject-seqs"
        repo.save_session(self._sample_session(session_id))

        # Non-zero sequence_number rejected
        ev1 = self._sample_event(session_id, sequence_number=42)
        with pytest.raises(ValueError, match="sequence_number"):
            repo.record_event(ev1)

        # Non-zero agent_sequence rejected
        ev2 = SessionEvent(
            session_id=session_id,
            agent_id="agent-1",
            tool_id="file_read",
            decision=Decision.ALLOW,
            agent_sequence=99,
        )
        with pytest.raises(ValueError, match="agent_sequence"):
            repo.record_event(ev2)

    def test_sequence_monotonicity_does_not_require_gaplessness(self) -> None:
        """Contract requires strictly monotonic ordering (S_later > S_earlier) without mandating gapless integers."""
        repo = self.create_repository()
        session_id = "sess-non-gapless"
        agent_id = "agent-gapless"
        repo.save_session(self._sample_session(session_id, agent_id=agent_id))
        now = datetime.now(timezone.utc)

        e1 = repo.record_event(
            self._sample_event(session_id, timestamp=now, agent_id=agent_id)
        )
        e2 = repo.record_event(
            self._sample_event(
                session_id, timestamp=now + timedelta(seconds=1), agent_id=agent_id
            )
        )
        assert e1.agent_sequence == 1
        assert e2.agent_sequence == 2

        # Prune event 1; sequence counters do not reset or renumber survivors
        repo.prune_events(cutoff=now + timedelta(seconds=1))
        e3 = repo.record_event(
            self._sample_event(
                session_id, timestamp=now + timedelta(seconds=2), agent_id=agent_id
            )
        )
        assert e3.agent_sequence == 3

        # List eligible events over surviving events (2, 3): monotonically increasing
        query = HorizonQuery(
            agent_id=agent_id,
            scope=AggregationScope.AGENT,
            window_seconds=60.0,
            evaluation_time=now + timedelta(seconds=5),
            baseline_agent_sequence=0,
        )
        events = repo.list_eligible_events(query)
        assert len(events) == 2
        assert [e.agent_sequence for e in events] == [2, 3]

        # Verify strict monotonicity invariant: S_later > S_earlier
        for i in range(len(events) - 1):
            assert events[i + 1].agent_sequence > events[i].agent_sequence

        # Watermark filtering against sequence gaps
        wm_query = HorizonQuery(
            agent_id=agent_id,
            scope=AggregationScope.AGENT,
            window_seconds=60.0,
            evaluation_time=now + timedelta(seconds=5),
            baseline_agent_sequence=2,
        )
        wm_events = repo.list_eligible_events(wm_query)
        assert len(wm_events) == 1
        assert wm_events[0].agent_sequence == 3

    def test_record_event_rejects_nonexistent_session(self) -> None:
        """Attempting to record an event for a non-existent session must fail closed with SessionNotFoundError."""
        repo = self.create_repository()
        event = self._sample_event("nonexistent-session")
        with pytest.raises(SessionNotFoundError):
            repo.record_event(event)

    def test_record_event_rejects_owner_mismatch(self) -> None:
        """Attempting to record an event with mismatched agent_id must fail closed with SessionBindingError."""
        repo = self.create_repository()
        session_id = "sess-owner-mismatch"
        repo.save_session(self._sample_session(session_id, agent_id="agent-owner"))

        event = SessionEvent(
            session_id=session_id,
            agent_id="agent-intruder",
            tool_id="file_read",
            decision=Decision.ALLOW,
        )
        with pytest.raises(SessionBindingError):
            repo.record_event(event)

    def test_record_event_rejects_terminal_session(self) -> None:
        """Attempting to record an event on a terminal session must fail closed with SessionTerminalError."""
        repo = self.create_repository()
        session_id = "sess-term-reject"
        repo.save_session(self._sample_session(session_id))
        repo.terminalize_session(session_id, self._sample_tombstone(session_id))

        with pytest.raises(SessionTerminalError):
            repo.record_event(self._sample_event(session_id))

    def test_record_event_atomically_touches_last_activity(self) -> None:
        """Recording an event atomically updates the active session's last_activity_at timestamp."""
        repo = self.create_repository()
        session_id = "sess-touch"
        t0 = datetime(2026, 9, 25, 10, 0, 0, tzinfo=timezone.utc)
        repo.save_session(
            Session(
                session_id=session_id,
                agent_id="agent-1",
                started_at=t0,
                last_activity_at=t0,
            )
        )

        t1 = datetime(2026, 9, 25, 10, 5, 0, tzinfo=timezone.utc)
        repo.record_event(self._sample_event(session_id, timestamp=t1))

        sess = repo.get_session(session_id)
        assert sess is not None
        assert sess.last_activity_at == t1

    def test_agent_scoped_query_aggregates_across_sessions(self) -> None:
        """HorizonQuery with scope=AGENT returns all events for the agent ordered by agent_sequence ASC."""
        repo = self.create_repository()
        repo.save_session(self._sample_session("sess-a1", agent_id="agent-1"))
        repo.save_session(self._sample_session("sess-a2", agent_id="agent-1"))
        now = datetime.now(timezone.utc)

        repo.record_event(
            self._sample_event("sess-a1", timestamp=now, agent_id="agent-1")
        )
        repo.record_event(
            self._sample_event(
                "sess-a2", timestamp=now + timedelta(seconds=1), agent_id="agent-1"
            )
        )
        repo.record_event(
            self._sample_event(
                "sess-a1", timestamp=now + timedelta(seconds=2), agent_id="agent-1"
            )
        )

        query = HorizonQuery(
            agent_id="agent-1",
            scope=AggregationScope.AGENT,
            window_seconds=60.0,
            evaluation_time=now + timedelta(seconds=5),
            baseline_agent_sequence=0,
        )
        events = repo.list_eligible_events(query)
        assert len(events) == 3
        assert [e.session_id for e in events] == ["sess-a1", "sess-a2", "sess-a1"]
        assert [e.agent_sequence for e in events] == [1, 2, 3]
        # Scope AGENT deterministically orders by agent_sequence ASC
        assert sorted(events, key=lambda e: e.agent_sequence) == events

    def test_session_scoped_query_isolates_single_session(self) -> None:
        """HorizonQuery with scope=SESSION isolates evidence to the specified session_id."""
        repo = self.create_repository()
        repo.save_session(self._sample_session("sess-1", agent_id="agent-1"))
        repo.save_session(self._sample_session("sess-2", agent_id="agent-1"))
        now = datetime.now(timezone.utc)

        repo.record_event(
            self._sample_event("sess-1", timestamp=now, agent_id="agent-1")
        )
        repo.record_event(
            self._sample_event(
                "sess-2", timestamp=now + timedelta(seconds=1), agent_id="agent-1"
            )
        )
        repo.record_event(
            self._sample_event(
                "sess-1", timestamp=now + timedelta(seconds=2), agent_id="agent-1"
            )
        )

        query = HorizonQuery(
            agent_id="agent-1",
            scope=AggregationScope.SESSION,
            session_id="sess-1",
            window_seconds=60.0,
            evaluation_time=now + timedelta(seconds=5),
            baseline_agent_sequence=0,
        )
        events = repo.list_eligible_events(query)
        assert len(events) == 2
        assert all(e.session_id == "sess-1" for e in events)
        assert [e.sequence_number for e in events] == [1, 2]
        # Scope SESSION deterministically orders by sequence_number ASC
        assert sorted(events, key=lambda e: e.sequence_number) == events

    def test_horizon_query_excludes_events_outside_window(self) -> None:
        """Events outside the temporal sliding window (timestamp < evaluation_time - window_seconds) are excluded."""
        repo = self.create_repository()
        repo.save_session(self._sample_session("sess-win", agent_id="agent-1"))
        t_eval = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)

        t_old = t_eval - timedelta(seconds=120)
        t_in = t_eval - timedelta(seconds=30)

        repo.record_event(
            self._sample_event("sess-win", timestamp=t_old, agent_id="agent-1")
        )
        e_in = repo.record_event(
            self._sample_event("sess-win", timestamp=t_in, agent_id="agent-1")
        )

        query = HorizonQuery(
            agent_id="agent-1",
            scope=AggregationScope.SESSION,
            session_id="sess-win",
            window_seconds=60.0,
            evaluation_time=t_eval,
            baseline_agent_sequence=0,
        )
        events = repo.list_eligible_events(query)
        assert len(events) == 1
        assert events[0].agent_sequence == e_in.agent_sequence
        assert events[0].timestamp == t_in

    def test_horizon_query_snapshot_semantics_excludes_future_events(self) -> None:
        """Snapshot semantics: evaluation_time - window <= event.timestamp <= evaluation_time.

        Verifies:
        - event.timestamp < evaluation_time -> included (if within window)
        - event.timestamp == evaluation_time -> included
        - event.timestamp > evaluation_time -> strictly excluded
        """
        repo = self.create_repository()
        repo.save_session(self._sample_session("sess-snap", agent_id="agent-1"))
        t_eval = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)

        t_past = t_eval - timedelta(seconds=10)
        t_exact = t_eval
        t_future = t_eval + timedelta(seconds=1)

        repo.record_event(
            self._sample_event("sess-snap", timestamp=t_past, agent_id="agent-1")
        )
        repo.record_event(
            self._sample_event("sess-snap", timestamp=t_exact, agent_id="agent-1")
        )
        repo.record_event(
            self._sample_event("sess-snap", timestamp=t_future, agent_id="agent-1")
        )

        query = HorizonQuery(
            agent_id="agent-1",
            scope=AggregationScope.SESSION,
            session_id="sess-snap",
            window_seconds=60.0,
            evaluation_time=t_eval,
            baseline_agent_sequence=0,
        )
        events = repo.list_eligible_events(query)
        assert len(events) == 2
        assert [e.timestamp for e in events] == [t_past, t_exact]

    def test_reinstatement_watermark_isolates_pre_baseline_events(self) -> None:
        """Events with agent_sequence <= baseline_agent_sequence are excluded from horizon eligibility."""
        repo = self.create_repository()
        repo.save_session(self._sample_session("sess-wm", agent_id="agent-1"))
        now = datetime.now(timezone.utc)

        repo.record_event(
            self._sample_event("sess-wm", timestamp=now, agent_id="agent-1")
        )
        repo.record_event(
            self._sample_event(
                "sess-wm", timestamp=now + timedelta(seconds=1), agent_id="agent-1"
            )
        )
        e3 = repo.record_event(
            self._sample_event(
                "sess-wm", timestamp=now + timedelta(seconds=2), agent_id="agent-1"
            )
        )

        # Baseline watermark at 2 -> only agent_sequence > 2 eligible
        query = HorizonQuery(
            agent_id="agent-1",
            scope=AggregationScope.SESSION,
            session_id="sess-wm",
            window_seconds=60.0,
            evaluation_time=now + timedelta(seconds=5),
            baseline_agent_sequence=2,
        )
        events = repo.list_eligible_events(query)
        assert len(events) == 1
        assert events[0].agent_sequence == 3
        assert events[0].agent_sequence == e3.agent_sequence

    def test_horizon_query_validation_contract(self) -> None:
        """HorizonQuery enforces domain constraints via Pydantic model validation."""
        now = datetime.now(timezone.utc)

        # SESSION scope requires session_id
        with pytest.raises(ValidationError):
            HorizonQuery(
                agent_id="agent-1",
                scope=AggregationScope.SESSION,
                session_id=None,
                window_seconds=60.0,
                evaluation_time=now,
                baseline_agent_sequence=0,
            )

        # AGENT scope forbids session_id
        with pytest.raises(ValidationError):
            HorizonQuery(
                agent_id="agent-1",
                scope=AggregationScope.AGENT,
                session_id="sess-forbidden",
                window_seconds=60.0,
                evaluation_time=now,
                baseline_agent_sequence=0,
            )

        # window_seconds must be gt 0
        with pytest.raises(ValidationError):
            HorizonQuery(
                agent_id="agent-1",
                scope=AggregationScope.AGENT,
                window_seconds=0.0,
                evaluation_time=now,
                baseline_agent_sequence=0,
            )

        # baseline_agent_sequence must be ge 0
        with pytest.raises(ValidationError):
            HorizonQuery(
                agent_id="agent-1",
                scope=AggregationScope.AGENT,
                window_seconds=60.0,
                evaluation_time=now,
                baseline_agent_sequence=-1,
            )

    def test_prune_events_preserves_sequence_continuity(self) -> None:
        """Pruning older events must never reset or modify sequence counters for surviving/future events."""
        repo = self.create_repository()
        session_id = "sess-prune-cont"
        repo.save_session(self._sample_session(session_id, agent_id="agent-1"))
        t1 = datetime(2026, 9, 25, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 25, 10, 5, 0, tzinfo=timezone.utc)

        e1 = repo.record_event(
            self._sample_event(session_id, timestamp=t1, agent_id="agent-1")
        )
        e2 = repo.record_event(
            self._sample_event(session_id, timestamp=t2, agent_id="agent-1")
        )
        assert e1.sequence_number == 1
        assert e1.agent_sequence == 1
        assert e2.sequence_number == 2
        assert e2.agent_sequence == 2

        # Evict everything
        cutoff_future = datetime(2026, 9, 25, 11, 0, 0, tzinfo=timezone.utc)
        evicted = repo.prune_events(cutoff=cutoff_future)
        assert evicted == 2
        assert repo.list_events(session_id) == []

        # Next recorded event MUST receive sequence_number=3 and agent_sequence=3
        t3 = datetime(2026, 9, 25, 11, 5, 0, tzinfo=timezone.utc)
        e3 = repo.record_event(
            self._sample_event(session_id, timestamp=t3, agent_id="agent-1")
        )
        assert e3.sequence_number == 3
        assert e3.agent_sequence == 3

    def test_update_event_final_decision_immutability(self) -> None:
        """Final decision supports None -> Decision, idempotent re-finalization, and rejects conflicting mutations."""
        repo = self.create_repository()
        session_id = "sess-fd-immut"
        repo.save_session(self._sample_session(session_id))
        ev = repo.record_event(self._sample_event(session_id))
        assert ev.final_decision is None

        # None -> Decision.APPROVAL_REQUIRED succeeds
        repo.update_event_final_decision(
            session_id=session_id,
            sequence_number=ev.sequence_number,
            final_decision=Decision.APPROVAL_REQUIRED,
        )

        # Idempotent re-finalization succeeds
        repo.update_event_final_decision(
            session_id=session_id,
            sequence_number=ev.sequence_number,
            final_decision=Decision.APPROVAL_REQUIRED,
        )

        # Conflicting mutation fails closed
        with pytest.raises(ValueError, match="already finalized"):
            repo.update_event_final_decision(
                session_id=session_id,
                sequence_number=ev.sequence_number,
                final_decision=Decision.DENY,
            )

        events = repo.list_events(session_id)
        assert events[0].final_decision == Decision.APPROVAL_REQUIRED

    def test_agent_sequence_isolated_between_agents(self) -> None:
        """Event recording for Agent A advances Agent A's sequence without affecting Agent B."""
        repo = self.create_repository()
        repo.save_session(self._sample_session("sess-a", agent_id="agent-a"))
        repo.save_session(self._sample_session("sess-b", agent_id="agent-b"))

        ea1 = repo.record_event(self._sample_event("sess-a", agent_id="agent-a"))
        ea2 = repo.record_event(self._sample_event("sess-a", agent_id="agent-a"))
        ea3 = repo.record_event(self._sample_event("sess-a", agent_id="agent-a"))

        eb1 = repo.record_event(self._sample_event("sess-b", agent_id="agent-b"))
        eb2 = repo.record_event(self._sample_event("sess-b", agent_id="agent-b"))

        assert [ea1.agent_sequence, ea2.agent_sequence, ea3.agent_sequence] == [1, 2, 3]
        assert [eb1.agent_sequence, eb2.agent_sequence] == [1, 2]

    def test_pruning_preserves_watermark_semantics(self) -> None:
        """Physical eviction of pre-baseline events does not break watermark filtering on survivors."""
        repo = self.create_repository()
        session_id = "sess-pw"
        agent_id = "agent-pw"
        repo.save_session(self._sample_session(session_id, agent_id=agent_id))
        now = datetime.now(timezone.utc)

        t1 = now
        t2 = now + timedelta(seconds=1)
        t3 = now + timedelta(seconds=2)

        repo.record_event(
            self._sample_event(session_id, timestamp=t1, agent_id=agent_id)
        )
        repo.record_event(
            self._sample_event(session_id, timestamp=t2, agent_id=agent_id)
        )
        repo.record_event(
            self._sample_event(session_id, timestamp=t3, agent_id=agent_id)
        )

        # Prune event 1 physically
        repo.prune_events(cutoff=t2)
        survivors = repo.list_events(session_id)
        assert len(survivors) == 2
        assert [e.agent_sequence for e in survivors] == [2, 3]

        # Query with baseline watermark = 2 returns only event 3
        query = HorizonQuery(
            agent_id=agent_id,
            scope=AggregationScope.SESSION,
            session_id=session_id,
            window_seconds=60.0,
            evaluation_time=now + timedelta(seconds=5),
            baseline_agent_sequence=2,
        )
        eligible = repo.list_eligible_events(query)
        assert len(eligible) == 1
        assert eligible[0].agent_sequence == 3

    def test_concurrent_record_event_allocates_unique_agent_sequences(self) -> None:
        """Concurrent record_event calls for the same agent allocate unique, strictly monotonic sequences."""
        import threading

        repo = self.create_repository()
        agent_id = "agent-concurrent-seq"
        repo.save_session(self._sample_session("sess-c1", agent_id=agent_id))
        repo.save_session(self._sample_session("sess-c2", agent_id=agent_id))

        recorded_events = []
        errors = []

        def worker(sess_id: str):
            try:
                e = repo.record_event(self._sample_event(sess_id, agent_id=agent_id))
                recorded_events.append(e)
            except Exception as exc:
                errors.append(exc)

        # 20 threads across two sessions for the same agent
        threads = [
            threading.Thread(
                target=worker, args=(f"sess-c{1 if i % 2 == 0 else 2}",)
            )
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(recorded_events) == 20
        agent_sequences = [e.agent_sequence for e in recorded_events]
        # Invariant 1: all allocated agent_sequence values are unique
        assert len(set(agent_sequences)) == len(recorded_events)
        # Invariant 2: strictly monotonic ordering holds across committed sequence allocations
        sorted_sequences = sorted(agent_sequences)
        for i in range(len(sorted_sequences) - 1):
            assert sorted_sequences[i + 1] > sorted_sequences[i]

    def test_terminalization_races_with_record_event(self) -> None:
        """Racing record_event and terminalize_session guarantees no event ever commits on a terminal session."""
        import threading

        repo = self.create_repository()
        session_id = "sess-race-term"
        agent_id = "agent-race"
        repo.save_session(self._sample_session(session_id, agent_id=agent_id))
        tombstone = self._sample_tombstone(session_id, agent_id=agent_id)

        recorded = []
        terminal_errors = []
        terminalized = []

        def event_worker():
            try:
                ev = repo.record_event(
                    self._sample_event(session_id, agent_id=agent_id)
                )
                recorded.append(ev)
            except SessionTerminalError as exc:
                terminal_errors.append(exc)

        def term_worker():
            res = repo.terminalize_session(session_id, tombstone)
            terminalized.append(res)

        threads = [threading.Thread(target=event_worker) for _ in range(15)]
        term_thread = threading.Thread(target=term_worker)
        threads.append(term_thread)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Session is now terminal
        assert repo.get_session(session_id) is None
        assert repo.get_tombstone(session_id) is not None

        # Any event recorded must have committed strictly before terminalization
        persisted_events = repo.list_events(session_id)
        assert len(persisted_events) == len(recorded)
        # Post-terminalization record attempt must fail closed
        with pytest.raises(SessionTerminalError):
            repo.record_event(self._sample_event(session_id, agent_id=agent_id))
