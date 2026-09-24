"""Integration tests for AuditService and AuditEvidenceRepository (PR #182).

Verifies:
1. Repository Authority: AuditEvidenceRepository is the sole authoritative state source.
   AuditService holds no independent internal collection (no `_events`).
2. Protocol Delegation: AuditService methods delegate directly to repository protocol methods.
3. Immutability & Defensive Copying: Mutations on caller references or returned objects
   cannot alter persisted evidence.
4. Deterministic Ordering: Events are returned in chronological (timestamp, event_id) order.
5. Query Filtering: Filtering by session_id, agent_id, limit, and offset.
6. Architectural Boundary: AuditService imports zero concrete repository adapters.
"""

import ast
from datetime import datetime, timezone
from pathlib import Path

from app.models.audit_event import AuditEvent, Decision
from app.repositories.in_memory.audit_evidence_repository import (
    InMemoryAuditEvidenceRepository,
)
from app.repositories.interfaces.audit_evidence_repository import (
    AuditEvidenceRepository,
)
from app.services.audit_service import AuditService


def make_audit_event(
    event_id: str = "evt-100",
    session_id: str = "sess-1",
    agent_id: str = "agent-1",
    tool_id: str = "file_read",
    decision: Decision = Decision.ALLOW,
    timestamp: datetime | None = None,
) -> AuditEvent:
    kwargs = {
        "event_id": event_id,
        "session_id": session_id,
        "agent_id": agent_id,
        "tool_id": tool_id,
        "decision": decision,
    }
    if timestamp is not None:
        kwargs["timestamp"] = timestamp
    return AuditEvent(**kwargs)


class TestAuditRepositoryAuthority:
    """Verifies that AuditEvidenceRepository is the authoritative state store."""

    def test_record_event_persists_to_repository_and_service_has_no_independent_copy(
        self,
    ) -> None:
        repo = InMemoryAuditEvidenceRepository()
        service = AuditService(audit_repository=repo)

        # Invariant: AuditService must not retain an internal _events list
        assert not hasattr(service, "_events")

        event = make_audit_event("evt-auth-1")
        returned = service.record_event(event)

        # Invariant: record_event returns the supplied event
        assert returned is event

        # Authoritative persistence in repository
        assert repo.get("evt-auth-1") is not None
        assert repo.get("evt-auth-1").event_id == "evt-auth-1"

        queried = repo.query(session_id="sess-1")
        assert len(queried) == 1
        assert queried[0].event_id == "evt-auth-1"

        # Service read path reflects repository state
        assert len(service.list_events()) == 1
        assert service.get_event("evt-auth-1") is not None

    def test_service_delegates_to_repository_protocol(self) -> None:
        """Verifies direct protocol delegation using a spy repository."""

        class SpyAuditEvidenceRepository(AuditEvidenceRepository):
            def __init__(self) -> None:
                self.appended: list[AuditEvent] = []
                self.get_calls: list[str] = []
                self.query_calls: list[dict] = []

            def append(self, event: AuditEvent) -> None:
                self.appended.append(event)

            def get(self, event_id: str) -> AuditEvent | None:
                self.get_calls.append(event_id)
                for ev in self.appended:
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
                self.query_calls.append(
                    {
                        "session_id": session_id,
                        "agent_id": agent_id,
                        "limit": limit,
                        "offset": offset,
                    }
                )
                filtered = self.appended
                if session_id:
                    filtered = [e for e in filtered if e.session_id == session_id]
                if agent_id:
                    filtered = [e for e in filtered if e.agent_id == agent_id]
                return filtered[offset : offset + limit]

        spy_repo = SpyAuditEvidenceRepository()
        service = AuditService(audit_repository=spy_repo)

        event = make_audit_event(
            "evt-spy-1", session_id="sess-spy", agent_id="agent-spy"
        )
        service.record_event(event)

        assert len(spy_repo.appended) == 1
        assert spy_repo.appended[0].event_id == "evt-spy-1"

        # Test get_event delegation
        res = service.get_event("evt-spy-1")
        assert res is not None
        assert spy_repo.get_calls == ["evt-spy-1"]

        # Test list_events delegation with kwargs
        service.list_events(
            session_id="sess-spy", agent_id="agent-spy", limit=10, offset=1
        )
        assert len(spy_repo.query_calls) == 1
        assert spy_repo.query_calls[0] == {
            "session_id": "sess-spy",
            "agent_id": "agent-spy",
            "limit": 10,
            "offset": 1,
        }


class TestAuditImmutabilityAndDefensiveCopies:
    """Verifies bidirectional isolation: caller -> repository and repository -> caller."""

    def test_persisted_evidence_isolated_from_subsequent_caller_mutation(self) -> None:
        repo = InMemoryAuditEvidenceRepository()
        service = AuditService(audit_repository=repo)

        event = make_audit_event("evt-defensive-1")
        service.record_event(event)

        # Verify repository holds a distinct copy
        stored = repo.get("evt-defensive-1")
        assert stored is not None
        assert stored == event
        assert stored is not event

    def test_repository_read_isolated_from_subsequent_read_mutation(self) -> None:
        repo = InMemoryAuditEvidenceRepository()
        service = AuditService(audit_repository=repo)

        event = make_audit_event("evt-defensive-2")
        service.record_event(event)

        first_read = service.get_event("evt-defensive-2")
        second_read = service.get_event("evt-defensive-2")
        assert first_read is not None
        assert second_read is not None
        assert first_read is not second_read
        assert first_read == second_read


class TestAuditOrderingAndFiltering:
    """Verifies deterministic sorting and query filtering."""

    def test_deterministic_chronological_ordering(self) -> None:
        repo = InMemoryAuditEvidenceRepository()
        service = AuditService(audit_repository=repo)

        t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Record out of order: t2, t3, t1
        service.record_event(make_audit_event("evt-2", timestamp=t2))
        service.record_event(make_audit_event("evt-3", timestamp=t3))
        service.record_event(make_audit_event("evt-1", timestamp=t1))

        events = service.list_events()
        assert [e.event_id for e in events] == ["evt-1", "evt-2", "evt-3"]

    def test_pagination_limit_and_offset(self) -> None:
        repo = InMemoryAuditEvidenceRepository()
        service = AuditService(audit_repository=repo)

        for i in range(5):
            t = datetime(2026, 1, 1, 10, i, 0, tzinfo=timezone.utc)
            service.record_event(make_audit_event(f"evt-{i}", timestamp=t))

        page1 = service.list_events(limit=2, offset=0)
        assert [e.event_id for e in page1] == ["evt-0", "evt-1"]

        page2 = service.list_events(limit=2, offset=2)
        assert [e.event_id for e in page2] == ["evt-2", "evt-3"]

        page3 = service.list_events(limit=2, offset=4)
        assert [e.event_id for e in page3] == ["evt-4"]


class TestAuditServiceAstBoundary:
    """Guarantees AuditService depends exclusively on Protocol interfaces, never concrete adapters."""

    def test_audit_service_imports_no_concrete_repositories(self) -> None:
        service_path = Path("app/services/audit_service.py")
        tree = ast.parse(service_path.read_text())

        forbidden_modules = {
            "app.repositories.in_memory",
            "app.repositories.sql",
            "app.repositories.sqlite",
            "app.repositories.postgres",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_modules:
                        assert not alias.name.startswith(forbidden), (
                            f"Forbidden import '{alias.name}' found in {service_path}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_modules:
                        assert not node.module.startswith(forbidden), (
                            f"Forbidden import '{node.module}' found in {service_path}"
                        )
