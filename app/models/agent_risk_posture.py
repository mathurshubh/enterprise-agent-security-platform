"""Agent-scoped enforcement posture (M2b).

The platform keeps two derived views of the same authoritative findings:

``RiskAssessment`` (session-scoped)
    What happened in one session, for reporting and attribution. Unchanged.

``AgentRiskPosture`` (agent-scoped)
    What the agent's accumulated behaviour means for enforcement. This is what the
    response decision is derived from, so rotating to a fresh ``session_id`` cannot
    present an agent as newly harmless (finding H-3).

A posture is derived state: ``Finding`` remains the authoritative evidence. Findings
recorded at or before ``baseline_at`` stay evidence but no longer drive enforcement,
which is how reinstatement resets enforcement eligibility without erasing history.
"""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.finding import Severity
from app.models.risk_assessment import RiskLevel


class PostureState(str, Enum):
    """Lifecycle state of an agent's materialized risk posture projection (M5-B)."""

    UNINITIALIZED = "UNINITIALIZED"
    HEALTHY = "HEALTHY"
    STALE = "STALE"


class AgentRiskPosture(BaseModel):
    """Derived, process-local enforcement posture for one agent."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    state: PostureState = PostureState.HEALTHY
    risk_score: int = Field(default=0, ge=0)
    risk_level: RiskLevel = RiskLevel.LOW
    finding_count: int = Field(default=0, ge=0)
    baseline_at: datetime | None = None
    baseline_sequence: int = Field(default=0, ge=0)
    last_applied_sequence: int = Field(default=0, ge=0)
    counts_by_severity: dict[Severity, int] = Field(
        default_factory=lambda: {s: 0 for s in Severity}
    )
    counts_by_rule: dict[str, int] = Field(default_factory=dict)
    posture_version: int = Field(default=1, ge=1)
    assessed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
