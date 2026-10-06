"""InMemoryAdministrativeAuditRepository — in-memory adapter for administrative refusal evidence.

ADR-028 §6, ADR-034 §8.
"""

from threading import RLock

from app.models.administrative_audit_event import AdministrativeAuditEvent
from app.repositories.interfaces.administrative_audit_repository import (
    AdministrativeAuditRepository,
)


class InMemoryAdministrativeAuditRepository(AdministrativeAuditRepository):
    """Thread-safe append-only store for refused administrative attempts.

    Invariants:
    - Append-Only: no operation replaces or removes a written record.
    - Object Isolation: stored and returned entities are defensive deep copies, so a
      caller holding a returned record cannot reach the stored one.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._events: list[AdministrativeAuditEvent] = []

    def record_event(self, event: AdministrativeAuditEvent) -> AdministrativeAuditEvent:
        with self._lock:
            self._events.append(event.model_copy(deep=True))
            return event.model_copy(deep=True)

    def list_events(
        self,
        agent_id: str | None = None,
    ) -> list[AdministrativeAuditEvent]:
        with self._lock:
            matching = [
                e for e in self._events if agent_id is None or e.agent_id == agent_id
            ]
            ordered = sorted(matching, key=lambda e: (e.occurred_at, e.event_id))
            return [e.model_copy(deep=True) for e in ordered]
