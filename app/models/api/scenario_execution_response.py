from datetime import datetime

from pydantic import BaseModel, Field

from app.models.scenario_evidence import ScenarioExecutionEvidence


class ScenarioExecutionResponse(BaseModel):
    """API representation of a scenario execution outcome."""

    execution_id: str
    scenario_id: str
    session_id: str
    execution_mode: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    error_message: str | None = None

    # Scenario Grading
    passed: bool | None = None
    mismatches: list[str] = Field(default_factory=list)

    # Authoritative Causal Security Evidence
    evidence: ScenarioExecutionEvidence | None = Field(
        default=None,
        description="Structured, authoritative security evidence across all evaluated pipeline phases.",
    )

    # Backward compatibility flat aliases
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
    observed_findings: list[str] = Field(default_factory=list)
