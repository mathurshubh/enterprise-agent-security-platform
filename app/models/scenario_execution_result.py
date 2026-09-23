from pydantic import BaseModel, Field


class ScenarioExecutionResult(BaseModel):
    """Encapsulates the security outcomes and grading assertions of a scenario run."""

    passed: bool
    authorization_decision: str = Field(
        description="The deterministic decision produced by authorization and policy checks."
    )
    final_decision: str | None = Field(
        default=None,
        description=(
            "The final security decision produced after evaluating detection findings and "
            "applying response actions. None if execution did not reach final-decision assignment."
        ),
    )
    observed_response: str
    observed_risk_level: str
    observed_findings: list[str]
    mismatches: list[str]
    observed_decision: str | None = Field(
        default=None,
        description=(
            "Legacy compatibility alias for final_decision. Represents the downstream pipeline "
            "outcome, not the authorization evaluation."
        ),
    )

