from pydantic import BaseModel


class ScenarioExecutionResult(BaseModel):
    """Encapsulates the security outcomes and grading assertions of a scenario run."""

    passed: bool
    observed_decision: str
    observed_response: str
    observed_risk_level: str
    observed_findings: list[str]
    mismatches: list[str]
