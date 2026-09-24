"""AuditEvidenceRepository — Domain persistence protocol for immutable Audit Evidence (ADR-028, ADR-030)."""

from typing import Protocol

from app.models.audit_event import AuditEvent


class AuditEvidenceRepository(Protocol):
    """Repository protocol for immutable, append-only Audit Evidence persistence (ADR-028, ADR-030).

    Invariants:
    - Append-only: No update() or delete() methods exist on this interface.
    - Independent attribution: Every event includes session_id, agent_id, decision,
      and timestamp, ensuring complete forensic attribution decoupled from session horizons.
    - Minimal query surface: Provides append, get, and query filtering without speculative operations.
    """

    def append(self, event: AuditEvent) -> None:
        """Append an immutable audit event to durable storage."""
        ...

    def get(self, event_id: str) -> AuditEvent | None:
        """Retrieve an audit event by its authoritative event_id, or None if not found."""
        ...

    def query(
        self,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        """Query audit events with optional filtering by session_id and/or agent_id."""
        ...
