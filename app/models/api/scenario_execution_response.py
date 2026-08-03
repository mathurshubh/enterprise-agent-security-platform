from datetime import datetime

from pydantic import BaseModel


class ScenarioExecutionResponse(BaseModel):
    """API representation of a scenario execution outcome."""

    execution_id: str
    scenario_id: str
    session_id: str
    execution_mode: str
    status: str
    passed: bool | None = None
    observed_decision: str | None = None
    observed_response: str | None = None
    observed_risk_level: str | None = None
    observed_findings: list[str] = []
    mismatches: list[str] = []
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
