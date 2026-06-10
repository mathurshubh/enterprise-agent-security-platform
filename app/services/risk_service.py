from app.models.finding import Finding, Severity
from app.models.risk_assessment import RiskAssessment, RiskLevel


class RiskService:
    def assess(
        self,
        findings: list[Finding],
    ) -> RiskAssessment:
        if not findings:
            raise ValueError("At least one finding is required")

        severity_weights = {
            Severity.LOW: 10,
            Severity.MEDIUM: 25,
            Severity.HIGH: 50,
            Severity.CRITICAL: 100,
        }

        risk_score = sum(
            severity_weights[finding.severity]
            for finding in findings
        )

        if risk_score >= 100:
            risk_level = RiskLevel.CRITICAL
        elif risk_score >= 50:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 25:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        first_finding = findings[0]

        return RiskAssessment(
            session_id=first_finding.session_id,
            agent_id=first_finding.agent_id,
            risk_score=risk_score,
            risk_level=risk_level,
            finding_count=len(findings),
        )
