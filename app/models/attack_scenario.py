from pydantic import BaseModel, Field

from app.models.risk_assessment import RiskLevel


class AttackScenario(BaseModel):
    scenario_id: str
    name: str
    session_id: str
    agent_id: str
    tool_sequence: list[str] = Field(default_factory=list)
    expected_findings: list[str] = Field(default_factory=list)
    expected_risk_level: RiskLevel