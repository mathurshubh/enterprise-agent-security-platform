from datetime import datetime
from pydantic import BaseModel

from app.models.execution_mode import ExecutionMode
from app.models.execution_status import ExecutionStatus
from app.models.scenario_execution_result import ScenarioExecutionResult


class ScenarioExecution(BaseModel):
    """Infrastructure-level metadata and tracking model for a scenario execution."""

    execution_id: str
    scenario_id: str
    session_id: str
    execution_mode: ExecutionMode
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    result: ScenarioExecutionResult | None = None
    error_message: str | None = None
