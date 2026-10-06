"""AdministrativeAuditRepository — persistence protocol for administrative refusal evidence.

ADR-028 §6, ADR-034 §8, ADR-030 L.3.
"""

from typing import Protocol

from app.models.administrative_audit_event import AdministrativeAuditEvent


class AdministrativeAuditUnavailableError(Exception):
    """Raised when administrative refusal evidence cannot be persisted.

    Its own error, because the caller's obligation differs from an ordinary storage
    failure: L.10 requires the operation to return 503, commit no administrative
    mutation, and never imply to the caller that the refusal was recorded.
    """


class AdministrativeAuditRepository(Protocol):
    """Append and read only. There is no update and no delete.

    Invariants:
    - Append-Only: the protocol exposes no mutation of a written record. Immutability is
      enforced by construction in the domain model and by the absence of a mutator here;
      a repository that cannot express a rewrite cannot be asked to perform one.
    - No Referential Participation: records carry no foreign keys, so an append never
      depends on, or is refused by, the current state of any control-plane table
      (ADR-034 §8.1).
    - Fail-Closed Reporting: a failed append raises rather than returning a value a
      caller might ignore.
    """

    def record_event(self, event: AdministrativeAuditEvent) -> AdministrativeAuditEvent:
        """Append one refusal record and return it as persisted."""
        ...

    def list_events(
        self,
        agent_id: str | None = None,
    ) -> list[AdministrativeAuditEvent]:
        """Return recorded refusals in deterministic chronological order."""
        ...
