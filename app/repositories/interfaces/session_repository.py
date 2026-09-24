"""SessionRepository — Domain persistence protocol unifying session lifecycle, tombstones, and detection horizon (ADR-027, ADR-030)."""

from datetime import datetime
from typing import Protocol

from app.models.session import Session, TerminalSessionTombstone
from app.models.session_event import SessionEvent


class SessionRepository(Protocol):
    """Repository protocol unifying session lifecycle, terminal tombstones, and detection horizon (ADR-027, ADR-030).

    Invariants:
    - No Arbitrary Deletion: Active sessions cannot be deleted out-of-band; they must
      transition via terminalize_session() to preserve ownership finality (M4-S-1).
    - Atomic Terminalization: Active session removal and tombstone persistence occur
      atomically under a single synchronization boundary (M4-S-2).
    - Permanent Tombstones: Tombstones are retained permanently and never evicted under capacity pressure (M4-S-6).
    - Rolling Horizon: Detection events maintain sliding window retention with canonical deterministic ordering.
    """

    def get_session(self, session_id: str) -> Session | None:
        """Retrieve an active session by session_id, or None if not found."""
        ...

    def save_session(self, session: Session) -> None:
        """Persist or update an active session."""
        ...

    def list_sessions(self) -> list[Session]:
        """List all active sessions."""
        ...

    def get_tombstone(self, session_id: str) -> TerminalSessionTombstone | None:
        """Retrieve a terminal session tombstone if it exists."""
        ...

    def save_tombstone(self, tombstone: TerminalSessionTombstone) -> None:
        """Persist a terminal session tombstone directly."""
        ...

    def terminalize_session(
        self,
        session_id: str,
        tombstone: TerminalSessionTombstone,
    ) -> bool:
        """Atomically remove an active session and persist its terminal tombstone.

        Returns True if the session was active and terminalized, or False if the session
        was not found or was already terminal.
        """
        ...

    def record_event(self, event: SessionEvent) -> None:
        """Record a detection horizon event for a session."""
        ...

    def list_events(self, session_id: str) -> list[SessionEvent]:
        """Return recorded events for a session in canonical deterministic order."""
        ...

    def prune_events(self, *, cutoff: datetime) -> int:
        """Prune detection horizon events older than the cutoff timestamp. Returns count evicted."""
        ...
