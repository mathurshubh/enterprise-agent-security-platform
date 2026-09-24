"""InMemoryAuditEvidenceRepository — In-memory adapter for immutable Audit Evidence (ADR-028, ADR-030)."""

from threading import RLock

from app.models.audit_event import AuditEvent
from app.repositories.interfaces.audit_evidence_repository import (
    AuditEvidenceRepository,
)


class InMemoryAuditEvidenceRepository(AuditEvidenceRepository):
    """Thread-safe in-memory repository for immutable Audit Evidence.

    Invariants:
    - Object Isolation: Stored and returned entities are defensive deep copies.
    - Append-Only: No update or delete operations exist.
    - Deterministic Ordering: query() sorts chronologically by (timestamp, event_id).
    - Missing Records: Non-existent entities return None.
    - Thread-Safe: Synchronized via threading.RLock.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event.model_copy(deep=True))

    def get(self, event_id: str) -> AuditEvent | None:
        with self._lock:
            for ev in self._events:
                if ev.event_id == event_id:
                    return ev.model_copy(deep=True)
            return None

    def query(
        self,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        with self._lock:
            filtered = self._events
            if session_id is not None:
                filtered = [e for e in filtered if e.session_id == session_id]
            if agent_id is not None:
                filtered = [e for e in filtered if e.agent_id == agent_id]

            # Deterministic ordering: primary key timestamp, secondary key event_id
            ordered = sorted(filtered, key=lambda e: (e.timestamp, e.event_id))
            sliced = ordered[offset : offset + limit]
            return [e.model_copy(deep=True) for e in sliced]
