"""Reusable contract tests for AuditEvidenceRepository implementations."""

import abc
from datetime import datetime, timezone

from app.models.audit_event import AuditEvent, Decision
from app.repositories.interfaces.audit_evidence_repository import (
    AuditEvidenceRepository,
)


class BaseAuditEvidenceRepositoryContractTests(abc.ABC):
    """Abstract contract test suite for any AuditEvidenceRepository adapter."""

    @abc.abstractmethod
    def create_repository(self) -> AuditEvidenceRepository:
        """Factory method to construct a fresh, empty repository under test."""
        raise NotImplementedError

    def _sample_event(
        self,
        event_id: str = "audit-1",
        session_id: str = "session-1",
        agent_id: str = "agent-1",
        timestamp: datetime | None = None,
    ) -> AuditEvent:
        return AuditEvent(
            event_id=event_id,
            session_id=session_id,
            agent_id=agent_id,
            tool_id="file_read",
            decision=Decision.ALLOW,
            timestamp=timestamp or datetime.now(timezone.utc),
        )

    def test_append_and_get_event(self) -> None:
        repo = self.create_repository()
        event = self._sample_event()

        repo.append(event)
        retrieved = repo.get(event.event_id)

        assert retrieved is not None
        assert retrieved.event_id == event.event_id
        assert retrieved.session_id == event.session_id
        assert retrieved.agent_id == event.agent_id
        assert retrieved.decision == event.decision

    def test_get_missing_event_returns_none(self) -> None:
        repo = self.create_repository()
        assert repo.get("non-existent-event") is None

    def test_query_filtering_by_session_and_agent(self) -> None:
        repo = self.create_repository()
        now = datetime.now(timezone.utc)

        e1 = self._sample_event("e-1", session_id="s-1", agent_id="a-1", timestamp=now)
        e2 = self._sample_event("e-2", session_id="s-1", agent_id="a-2", timestamp=now)
        e3 = self._sample_event("e-3", session_id="s-2", agent_id="a-1", timestamp=now)

        repo.append(e1)
        repo.append(e2)
        repo.append(e3)

        assert len(repo.query(session_id="s-1")) == 2
        assert len(repo.query(session_id="s-2")) == 1
        assert len(repo.query(agent_id="a-1")) == 2
        assert len(repo.query(session_id="s-1", agent_id="a-1")) == 1
        assert len(repo.query(session_id="unknown")) == 0

    def test_deterministic_ordering_with_timestamp_ties(self) -> None:
        """Events sharing equal timestamps must deterministically sort by (timestamp, event_id)."""
        repo = self.create_repository()
        same_time = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)

        # Append in non-sorted event_id order
        repo.append(self._sample_event("event-c", timestamp=same_time))
        repo.append(self._sample_event("event-a", timestamp=same_time))
        repo.append(self._sample_event("event-b", timestamp=same_time))

        results = repo.query()
        event_ids = [e.event_id for e in results]
        assert event_ids == ["event-a", "event-b", "event-c"]

    def test_query_pagination_limit_and_offset(self) -> None:
        repo = self.create_repository()
        base_time = datetime(2026, 9, 24, 10, 0, 0, tzinfo=timezone.utc)

        for i in range(5):
            repo.append(self._sample_event(f"e-{i:02d}", timestamp=base_time))

        page1 = repo.query(limit=2, offset=0)
        assert [e.event_id for e in page1] == ["e-00", "e-01"]

        page2 = repo.query(limit=2, offset=2)
        assert [e.event_id for e in page2] == ["e-02", "e-03"]

        page3 = repo.query(limit=2, offset=4)
        assert [e.event_id for e in page3] == ["e-04"]

    def test_append_only_invariants(self) -> None:
        """Audit repository protocol must not expose delete, update, or count methods."""
        assert not hasattr(AuditEvidenceRepository, "delete")
        assert not hasattr(AuditEvidenceRepository, "update")
        assert not hasattr(AuditEvidenceRepository, "count")

    def test_defensive_copy_isolation(self) -> None:
        """Stored and retrieved audit events must be isolated defensive copies."""
        repo = self.create_repository()
        event = self._sample_event("e-iso-1")
        repo.append(event)

        # Invariant: retrieved instance is not the same Python object as the appended event
        retrieved1 = repo.get("e-iso-1")
        assert retrieved1 is not None
        assert retrieved1 is not event

        # Invariant: successive reads produce distinct instances
        retrieved2 = repo.get("e-iso-1")
        assert retrieved2 is not None
        assert retrieved2 is not retrieved1

        # Verify query collection isolation
        query_res = repo.query()
        assert len(query_res) == 1
        assert query_res[0] is not event
        assert query_res[0] is not retrieved1
        query_res.clear()
        assert len(repo.query()) == 1
