"""Refusal evidence for administrative lifecycle operations (ADR-028 §6, ADR-034 §8).

One fact, one record. A **committed** administrative transition is evidence in the
administrative ledger (``AdministrativeTransition``) and is never also written here; a
**refused** attempt is written here and never enters a ledger.

This is a separate record rather than a widened ``AuditEvent``. ``AuditEvent`` keeps its
required ``session_id`` and ``requested_tool_id``; relaxing them to fit administrative
operations would weaken the tool-request contract, and inventing a synthetic session or
tool would assert facts that did not occur (ADR-034 §8.1).
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.agent_administrative import (
    Actor,
    AdministrativeAction,
    AdministrativeLifecycleState,
)


class AdministrativeRefusalCode(str, Enum):
    """Why an administrative operation was refused (ADR-028 §6.2).

    Covers refusals at the API authorization boundary and within the administrative
    service alike, since both reach a lifecycle decision and both owe evidence.
    """

    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    UNKNOWN_AGENT = "UNKNOWN_AGENT"
    STALE_VERSION = "STALE_VERSION"
    ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"
    ADMINISTRATIVE_STATE_UNAVAILABLE = "ADMINISTRATIVE_STATE_UNAVAILABLE"


class AdministrativeAuditEvent(BaseModel):
    """An immutable record of one refused administrative attempt.

    Invariants:
    - Refusals Only: a committed transition belongs in the administrative ledger. Writing
      both would make one fact two records that can disagree (ADR-028 §6.1).
    - No Referential Participation: holds no foreign key to ``agents``, administrative
      state, enforcement state, or any other control-plane table. Constraints express
      intra-record validity only, and interpreting the record requires no join
      (ADR-034 §8.1). ``agent_id`` is therefore a recorded string, not a reference, and
      remains meaningful for an agent that never existed.
    - Independent Of Evictable State: meaning never depends on the current registry or
      any lifecycle state. Observed state is recorded literally, at decision time.
    - Internal Evidence: recording a refusal never causes the API to reveal whether an
      agent exists (ADR-028 §6.2). Writing this record and answering the caller are
      separate decisions.
    - Immutable: enforced by construction, as for ``AuditEvent``.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str
    # A recorded identifier, not a reference. The attempt is evidence whether or not the
    # named agent exists -- UNKNOWN_AGENT is one of the refusals this record exists for.
    agent_id: str
    attempted_action: AdministrativeAction
    actor: Actor
    refusal_code: AdministrativeRefusalCode
    reason: str
    # The state observed when the decision was made, recorded literally. None where none
    # could be established, which is itself the fact being recorded.
    observed_state: AdministrativeLifecycleState | None = None
    correlation_id: str = Field(min_length=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
