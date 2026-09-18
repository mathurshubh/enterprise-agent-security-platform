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

from pydantic import BaseModel, ConfigDict, Field

from app.models.risk_assessment import RiskLevel


class AgentRiskPosture(BaseModel):
    """Derived, process-local enforcement posture for one agent."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    risk_score: int
    risk_level: RiskLevel
    finding_count: int
    baseline_at: datetime | None = None
    assessed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
