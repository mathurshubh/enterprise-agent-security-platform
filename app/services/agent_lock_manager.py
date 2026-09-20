"""Per-agent coordination lock manager (M5-B).

Provides thread-safe, per-agent coordination locks used across services
(EnforcementCoordinator, RuntimeService / Ingestion) to guarantee serializability
between finding acceptance + projection handoff and reinstatement + baseline reset.
"""

from threading import RLock


class AgentLockManager:
    """Manages per-agent reentrant locks for cross-service coordination."""

    def __init__(self) -> None:
        self._registry_lock = RLock()
        self._locks: dict[str, RLock] = {}

    def get_lock(self, agent_id: str) -> RLock:
        """Return the coordination lock for a given agent_id."""
        with self._registry_lock:
            lock = self._locks.get(agent_id)
            if lock is None:
                lock = RLock()
                self._locks[agent_id] = lock
            return lock
