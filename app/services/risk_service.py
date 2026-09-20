from threading import RLock

from app.models.finding import Finding, Severity
from app.models.risk_assessment import RiskAssessment, RiskLevel

SEVERITY_WEIGHTS = {
    Severity.LOW: 10,
    Severity.MEDIUM: 25,
    Severity.HIGH: 50,
    Severity.CRITICAL: 100,
}


def score_findings(findings: list[Finding]) -> int:
    """Return the deterministic weighted score for a set of findings."""
    return sum(SEVERITY_WEIGHTS[finding.severity] for finding in findings)


def level_for_score(risk_score: int) -> RiskLevel:
    """Map a score onto a risk level. Shared by session and agent scopes."""
    if risk_score >= 100:
        return RiskLevel.CRITICAL
    if risk_score >= 50:
        return RiskLevel.HIGH
    if risk_score >= 25:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


class AmbiguousAssessmentScopeError(ValueError):
    """Raised when an unscoped get_assessment query matches multiple agents for a session."""


class RiskService:
    """Session-scoped risk assessment for reporting and attribution.

    ``RiskAssessment`` is non-authoritative derived state; ``Finding`` is the
    authoritative security evidence. Assessments are process-local and stored in
    memory.

    This service is **not** an agent-posture authority. It held a second
    implementation of agent-scoped posture until M5-B.5, reachable only when a
    ``RuntimeService`` was constructed without a ``RiskAggregator``. That fallback
    and its posture API are gone: ``RiskAggregator`` is the sole authority for
    enforcement posture, and what remains here answers "what happened in this
    session", which the management plane reports and enforcement does not consult
    (ADR-024, ADR-026).
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._assessments: dict[tuple[str, str], RiskAssessment] = {}

    def assess_session(
        self,
        session_id: str,
        agent_id: str,
        findings: list[Finding],
    ) -> RiskAssessment:
        """Calculate and store a deterministic risk assessment for a specific session and agent.

        Enforces strict session and agent isolation. All findings must belong to the
        given session_id and agent_id. Derived assessment is stored under composite
        key (session_id, agent_id).
        """
        for finding in findings:
            if finding.session_id != session_id or finding.agent_id != agent_id:
                raise ValueError("All findings must belong to the requested session and agent")

        risk_score = score_findings(findings)
        risk_level = level_for_score(risk_score)

        assessment = RiskAssessment(
            session_id=session_id,
            agent_id=agent_id,
            risk_score=risk_score,
            risk_level=risk_level,
            finding_count=len(findings),
        )

        with self._lock:
            self._assessments[(session_id, agent_id)] = assessment

        return assessment

    def assess(
        self,
        findings: list[Finding],
    ) -> RiskAssessment:
        """Calculate a risk assessment for a list of findings (backwards compatibility)."""
        if not findings:
            raise ValueError("At least one finding is required")

        first_finding = findings[0]
        return self.assess_session(
            session_id=first_finding.session_id,
            agent_id=first_finding.agent_id,
            findings=findings,
        )

    def record_assessment(self, assessment: RiskAssessment) -> RiskAssessment:
        """Record a risk assessment directly in process-local state."""
        with self._lock:
            self._assessments[(assessment.session_id, assessment.agent_id)] = assessment
            return assessment

    def get_assessment(
        self,
        session_id: str,
        agent_id: str | None = None,
    ) -> RiskAssessment | None:
        """Retrieve process-local risk assessment for a session (and optional agent ID).

        If agent_id is omitted and multiple assessments exist for session_id across
        different agents, raises AmbiguousAssessmentScopeError.
        """
        with self._lock:
            if agent_id is not None:
                return self._assessments.get((session_id, agent_id))

            matching = [a for key, a in self._assessments.items() if key[0] == session_id]
            if len(matching) == 0:
                return None
            if len(matching) == 1:
                return matching[0]

            raise AmbiguousAssessmentScopeError(
                f"Multiple risk assessments exist for session '{session_id}'; agent_id is required"
            )

    def list_assessments(
        self,
        session_id: str | None = None,
        agent_id: str | None = None,
        risk_level: RiskLevel | None = None,
    ) -> list[RiskAssessment]:
        """List process-local risk assessments matching optional filters."""
        with self._lock:
            results = list(self._assessments.values())
            if session_id is not None:
                results = [r for r in results if r.session_id == session_id]
            if agent_id is not None:
                results = [r for r in results if r.agent_id == agent_id]
            if risk_level is not None:
                results = [r for r in results if r.risk_level == risk_level]
            return results

    def clear(self) -> None:
        """Clear process-local risk assessments (useful for testing)."""
        with self._lock:
            self._assessments.clear()

