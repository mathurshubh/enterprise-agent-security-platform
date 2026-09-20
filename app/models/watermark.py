"""Baseline watermark for enforcement epochs (M5-B).

A BaselineWatermark couples the temporal baseline timestamp and the evidence
sequence watermark into an immutable, serialized logical point.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

UNASSIGNED_SEQUENCE: int = 0


class BaselineWatermark(BaseModel):
    """Atomic snapshot of an agent's enforcement baseline boundary (B-10).

    Represents one serialized logical point:
        baseline_at: timezone-aware UTC datetime
        baseline_sequence: highest authoritative sequence belonging to evidence
                           at or before baseline_at.
    """

    model_config = ConfigDict(frozen=True)

    agent_id: str
    baseline_at: datetime | None = None
    baseline_sequence: int = Field(default=0, ge=0)
