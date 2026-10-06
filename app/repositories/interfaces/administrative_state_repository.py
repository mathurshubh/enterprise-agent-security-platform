"""AdministrativeStateRepository — persistence protocol for administrative lifecycle state.

ADR-024 A.6 (concurrency), A.8 (evidence); ADR-030 L.3 (persistence), AP.3, AP.4.
"""

from typing import Protocol

from app.models.agent_administrative import (
    AdministrativeTransition,
    AgentAdministrativeState,
)


class AdministrativeStateUnavailableError(Exception):
    """Raised when the administrative state authority or its storage is unavailable.

    Distinct from a refused transition. This says the plane's authoritative state could
    not be established, which L.10 surfaces as ``ADMINISTRATIVE_STATE_UNAVAILABLE`` and
    never as a lifecycle state: an unreachable repository is not a disabled agent.
    """


class AdministrativeTransitionInvariantError(Exception):
    """Raised when a transition violates an invariant rather than losing a race.

    Deliberately not representable as a ``False`` return. ``False`` means compare-and-set
    contention, which a caller repairs by re-reading and retrying; an illegal transition
    or a malformed version does not improve on retry, so a caller that cannot tell them
    apart will loop on a programming error (ADR-030 AP.4).
    """


class AdministrativeStateRepository(Protocol):
    """Repository protocol for administrative lifecycle state and its ledger.

    Invariants:
    - CAS Mutation: record_transition requires a mandatory expected_version keyword.
    - Strict Concurrency: the mutation succeeds if and only if the persisted version
      equals expected_version AND new_state.administrative_version equals
      expected_version + 1.
    - Atomicity: the state change and its ledger entry commit in one transaction. On a
      compare-and-set miss or a validation failure, neither is persisted, and the
      transition history is left exactly as it was.
    - Outcome Separation: a lost update returns False; an invariant violation raises
      AdministrativeTransitionInvariantError (AP.4).
    - Fail-Closed: storage failures surface as AdministrativeStateUnavailableError so the
      caller can fail closed rather than infer a state.
    - Absence Is Not A State: get_state returns None for an agent with no administrative
      record. None means "not establishable", never REGISTERED (L.3).
    """

    def get_state(self, agent_id: str) -> AgentAdministrativeState | None:
        """Return the agent's current administrative state, or None if no record exists."""
        ...

    def record_transition(
        self,
        transition: AdministrativeTransition,
        new_state: AgentAdministrativeState,
        *,
        expected_version: int,
    ) -> bool:
        """Atomically record an administrative transition and replace the state, under CAS.

        Args:
            transition: the append-only ledger record.
            new_state: the state to persist; its administrative_version must equal
                expected_version + 1.
            expected_version: the version the caller believes is persisted. 0 means the
                caller believes no record exists, which is how registration is expressed.

        Returns:
            True when the compare-and-set held and both the state and the ledger entry
            committed; False when the persisted version did not match expected_version.

        Raises:
            AdministrativeTransitionInvariantError: the transition is illegal under the
                administrative graph, or the offered version does not advance by exactly
                one. Not a retryable condition.
            AdministrativeStateUnavailableError: the storage is unavailable.
        """
        ...

    def list_transitions(
        self,
        agent_id: str | None = None,
    ) -> list[AdministrativeTransition]:
        """Return recorded administrative transitions in deterministic chronological order."""
        ...
