import warnings
from pydantic import BaseModel

from app.models.risk_assessment import RiskLevel

# Deprecated: ScenarioResult will be removed in a later release.
# Use ScenarioExecution and ScenarioExecutionResult instead.
warnings.warn(
    "ScenarioResult is deprecated and will be removed. Use ScenarioExecution instead.",
    DeprecationWarning,
    stacklevel=2,
)


class ScenarioResult(BaseModel):
    """Deprecated representation of a scenario result. Use ScenarioExecution instead."""

    scenario_id: str
    passed: bool
    observed_findings: list[str]
    observed_risk_level: RiskLevel