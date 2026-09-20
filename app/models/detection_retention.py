"""Detection retention models and policies (M4 Step 2C-B).

Defines the authoritative operational working window for raw SessionEvent retention,
governed by detection evaluation horizons rather than arbitrary capacity.
"""

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.services.detection_service import DetectionService


class DetectionRetentionPolicy(BaseModel):
    """Authoritative working-state retention policy derived from detection rule horizons (M4-EVENT)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    retention_window_seconds: float = Field(
        gt=0,
        description="Maximum evaluation horizon in seconds required across active detection rules.",
    )
    late_arrival_grace_seconds: float = Field(
        default=30.0,
        ge=0,
        description=(
            "Explicit allowance to absorb event delivery latency, scheduling jitter, "
            "clock skew, and limited out-of-order arrival."
        ),
    )
    rule_horizons: dict[str, float] = Field(
        default_factory=dict,
        description="Evaluation horizons contributed by specific detection rules.",
    )

    @property
    def total_retention_seconds(self) -> float:
        """Effective retention horizon guaranteeing complete detection coverage."""
        return self.retention_window_seconds + self.late_arrival_grace_seconds

    @classmethod
    def from_detection_service(
        cls,
        service: "DetectionService",
        *,
        late_arrival_grace_seconds: float = 30.0,
    ) -> "DetectionRetentionPolicy":
        """Derive policy from a DetectionService authority instance."""
        horizon = service.excessive_denials_window_seconds
        return cls(
            retention_window_seconds=horizon,
            late_arrival_grace_seconds=late_arrival_grace_seconds,
            rule_horizons={"EXCESSIVE_DENIALS": horizon},
        )
