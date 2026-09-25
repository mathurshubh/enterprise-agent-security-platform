"""EnforcementStateRepository — Domain persistence protocol for dynamic agent enforcement state (ADR-024, ADR-026, ADR-030)."""

from datetime import datetime
from typing import Protocol

from app.models.agent_enforcement import AgentEnforcementState, EnforcementTransition


class EnforcementStateUnavailableError(Exception):
    """Raised when the enforcement state authority or underlying storage is unavailable."""


class EnforcementStateRepository(Protocol):
    """Repository protocol for dynamic agent posture and monotonic epoch progression (ADR-024, ADR-026, ADR-030).

    Invariants:
    - CAS Mutation: record_transition requires a mandatory expected_epoch keyword argument.
    - Strict Concurrency: Mutation succeeds if and only if persisted_epoch == expected_epoch
      AND new_state.epoch == expected_epoch + 1.
    - Atomicity: State mutation and transition recording are committed atomically in the same
      durable transaction. On mismatch or failure, neither state nor transition is persisted.
    - Fail-Closed: Infrastructure or storage failures surface as EnforcementStateUnavailableError,
      allowing upstream authorization to fail closed.
    - Historical Derivation: get_epoch derives the count of reinstatements up to as_of for historical baseline audit.
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
            new_state: The new AgentEnforcementState to persist (must have epoch == expected_epoch + 1).
            expected_epoch: The mandatory expected current epoch.

        Returns:
            True if persisted_epoch == expected_epoch, new_state.epoch == expected_epoch + 1,
            and both state and transition committed atomically;
            False if an epoch mismatch occurred (stale replica CAS failure or invalid new_state.epoch).
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
