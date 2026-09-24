"""EnforcementStateRepository — Domain persistence protocol for dynamic agent enforcement state (ADR-024, ADR-026, ADR-030)."""

from datetime import datetime
from typing import Protocol

from app.models.agent_enforcement import AgentEnforcementState, EnforcementTransition


class EnforcementStateRepository(Protocol):
    """Repository protocol for dynamic agent posture and monotonic epoch progression (ADR-024, ADR-026, ADR-030).

    Invariants:
    - CAS Mutation: record_transition requires a mandatory expected_epoch keyword argument.
    - Strict Concurrency: Mutation succeeds if and only if persisted_epoch == expected_epoch.
      On commit, new_epoch == expected_epoch + 1 atomically.
    - No None escape hatch: Concurrent replicas with stale epochs fail closed and must re-evaluate.
    - Derivation: get_epoch derives the epoch at a specific timestamp from append-only transition history.
    """

    def get_state(self, agent_id: str) -> AgentEnforcementState | None:
        """Retrieve the current enforcement state for an agent, or None if not initialized."""
        ...

    def record_transition(
        self,
        transition: EnforcementTransition,
        new_state: AgentEnforcementState,
        *,
        expected_epoch: int,
    ) -> bool:
        """Atomically record an enforcement transition and update agent state under CAS.

        Args:
            transition: The append-only EnforcementTransition record.
            new_state: The new AgentEnforcementState to persist.
            expected_epoch: The mandatory expected current epoch.

        Returns:
            True if persisted_epoch == expected_epoch and the transition committed atomically;
            False if an epoch mismatch occurred (stale replica CAS failure).
        """
        ...

    def list_transitions(
        self,
        agent_id: str | None = None,
    ) -> list[EnforcementTransition]:
        """Return recorded enforcement transitions in chronological order."""
        ...

    def get_epoch(
        self,
        agent_id: str,
        *,
        as_of: datetime,
    ) -> int:
        """Derive the enforcement epoch for an agent at a given timestamp."""
        ...
