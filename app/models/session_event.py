from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.models.audit_event import Decision

UNASSIGNED_SEQUENCE: int = 0


class SessionEvent(BaseModel):
    """One recorded step in a session.

    ``(timestamp, sequence_number)`` is the canonical deterministic ordering key
    for a session's history. ``sequence_number`` is the **immutable per-session
    tie-breaker**: it does not replace chronological ordering, it decides the order
    of events chronology cannot separate.

    It is assigned once by ``SessionService`` when the event is recorded and never
    changed afterwards. It exists because two events in one session can share a
    timestamp, and ordering them by timestamp alone left the result dependent on
    internal heap layout rather than on the history itself. Anything that must read
    a session's events in a stable order depends on this field, so it is persisted
    with the event rather than recomputed by each reader.

    It is not derived from the timestamp and is not random. ``0`` means the event
    has not been recorded yet.

    Two decisions, deliberately separate. ``decision`` is what authorization and policy
    concluded, and is what detection evaluates; ``final_decision`` is what the pipeline
    concluded once the response action was applied. One field served both until the
    runtime rewrote it after detection had already run, which made live and replayed
    detection disagree about the same history: live saw the value detection was given,
    a later reader saw the value the response left behind.

    The final decision is causally downstream of detection -- detection produces the
    findings that produce the posture that produces the response -- so it cannot be
    detection's input for the same request. ``decision`` therefore stays as written.

    ``final_decision`` is ``None`` only when a request did not reach the point where the
    final decision is established. It is not a synonym for refusal: a refusal is an
    established outcome and records ``DENY``.
    """

    session_id: str
    agent_id: str
    tool_id: str
    decision: Decision

    sequence_number: int = Field(
        default=UNASSIGNED_SEQUENCE,
        ge=0,
        description=(
            "Monotonic 1-based position within the session, assigned exclusively "
            "by SessionService on record. 0 indicates an unrecorded event."
        ),
    )

    final_decision: Decision | None = Field(
        default=None,
        description=(
            "The decision after response enforcement, assigned once when the pipeline "
            "establishes it. None means the request did not reach that point."
        ),
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
