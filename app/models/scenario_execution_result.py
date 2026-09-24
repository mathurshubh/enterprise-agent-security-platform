from pydantic import BaseModel, ConfigDict, Field

from app.models.scenario_evidence import ScenarioExecutionEvidence


class ScenarioExecutionResult(BaseModel):
    """Encapsulates scenario grading assertions and authoritative execution evidence."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    mismatches: tuple[str, ...] = Field(default_factory=tuple)
    evidence: ScenarioExecutionEvidence

    @property
    def authorization_decision(self) -> str | None:
        """Deterministic authorization decision, or None if authorization was not reached."""
        return self.evidence.authorization.decision if self.evidence.authorization else None

    @property
    def final_decision(self) -> str | None:
        """Final pipeline outcome, or None if final decision assignment was not reached."""
        return self.evidence.final_decision.decision if self.evidence.final_decision else None

    @property
    def observed_decision(self) -> str | None:
        """Legacy compatibility alias for final_decision."""
        return self.final_decision

    @property
    def observed_response(self) -> str | None:
        """Recommended response action, or None if response step was not reached."""
        return self.evidence.response.action if self.evidence.response else None

    @property
    def observed_risk_level(self) -> str | None:
        """Assessed risk level, or None if risk assessment was not reached."""
        return self.evidence.risk.level if self.evidence.risk else None

    @property
    def observed_findings(self) -> list[str]:
        """List of observed finding rule names for legacy assertion compatibility."""
        if self.evidence.detection:
            return [f.rule_name for f in self.evidence.detection.findings]
        return []
