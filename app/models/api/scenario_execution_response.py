from datetime import datetime

from pydantic import BaseModel, Field


class ScenarioExecutionResponse(BaseModel):
    """API representation of a scenario execution outcome."""

    execution_id: str
    scenario_id: str
    session_id: str
    execution_mode: str
    status: str
    passed: bool | None = None
    authorization_decision: str | None = Field(
        default=None,
        description="Deterministic authorization decision evaluated before detection.",
    )
    final_decision: str | None = Field(
        default=None,
        description="Final pipeline outcome after detection and response action application.",
    )
    observed_decision: str | None = Field(
        default=None,
        description=(
            "Legacy compatibility alias for final_decision. Reflects final pipeline outcome, "
            "not authorization decision."
        ),
    )
    observed_response: str | None = None
    observed_risk_level: str | None = None
    observed_findings: list[str] = []
    mismatches: list[str] = []
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

