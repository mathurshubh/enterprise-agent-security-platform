"""Baseline watermark for enforcement epochs (M5-B).

A BaselineWatermark couples the temporal baseline timestamp with one watermark per
monotonic sequence namespace into an immutable, serialized logical point.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

UNASSIGNED_SEQUENCE: int = 0


class BaselineWatermark(BaseModel):
    """Atomic snapshot of an agent's enforcement baseline boundary (B-10).

    Represents one logical point, expressed once per namespace:
        baseline_at: timezone-aware UTC datetime
        baseline_evidence_sequence: highest ``Finding.evidence_sequence`` recorded at or
            before ``baseline_at``, allocated by ``FindingsService``
        baseline_agent_sequence: highest ``SessionEvent.agent_sequence`` recorded at or
            before ``baseline_at``, allocated by the session repository

    The two sequences are separate because their allocators are separate. A finding is
    derived from at least one event, so the two counters advance at different rates and
    their values are not interchangeable: comparing one against the other compares
    positions in different orderings. Each field is therefore named for the namespace it
    belongs to, and each consumer reads only its own — the risk projection reads
    ``baseline_evidence_sequence``, the detection horizon reads ``baseline_agent_sequence``.

    The two are captured from their own authorities and are not read atomically, so they
    may straddle concurrent activity by a small number of records. That is accepted: each
    watermark only has to be authoritative within its own namespace, and ``baseline_at``
    already carries the temporal boundary. Making them numerically simultaneous would
    require a transaction spanning both authorities, which this boundary does not need.
    """

    # extra="forbid" so a watermark cannot be constructed with a field name this model
    # does not define. Without it a stale or misspelled name is silently dropped and the
    # sequence defaults to 0, which reads as "exclude nothing" — a baseline that quietly
    # stops excluding is exactly the failure this separation exists to prevent.
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    baseline_at: datetime | None = None
    baseline_evidence_sequence: int = Field(default=0, ge=0)
    baseline_agent_sequence: int = Field(default=0, ge=0)
