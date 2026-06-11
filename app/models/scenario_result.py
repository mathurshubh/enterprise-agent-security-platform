from pydantic import BaseModel

from app.models.risk_assessment import RiskLevel


class ScenarioResult(BaseModel):
    scenario_id: str
    passed: bool
    observed_findings: list[str]
    observed_risk_level: RiskLevel