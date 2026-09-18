from datetime import datetime
from threading import RLock

from app.models.agent_risk_posture import AgentRiskPosture
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


class FindingScopeError(ValueError):
    """Raised when a finding presented for assessment belongs to another agent."""


class RiskService:
    """Service for calculating and maintaining process-local dynamic risk assessments.

    RiskAssessment is non-authoritative derived posture; Finding is the
    authoritative security evidence. Assessments are process-local and
    stored in memory.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._assessments: dict[tuple[str, str], RiskAssessment] = {}
        self._agent_postures: dict[str, AgentRiskPosture] = {}

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

    def assess_agent(
        self,
        agent_id: str,
        findings: list[Finding],
        baseline_at: datetime | None = None,
    ) -> AgentRiskPosture:
        """Calculate and store the enforcement posture for one agent.

        Accumulates across every session the agent has used, so a fresh ``session_id``
        cannot present an accumulated posture as new (finding H-3). Scoring is the same
        deterministic weighting the session assessment uses.

        ``baseline_at`` is recorded on the posture for attribution. Eligibility itself is
        applied by the caller through ``FindingsService.list_findings(recorded_after=…)``,
        because only the evidence store knows when a finding was accepted: detection
        rules set ``Finding.created_at`` deterministically, so it cannot separate
        historical evidence from evidence recorded after a reinstatement.

        Raises:
            FindingScopeError: a finding belongs to a different agent. Rejected rather
                than filtered, because a mismatch means the caller assembled the
                security input incorrectly.
        """
        for finding in findings:
            if finding.agent_id != agent_id:
                raise FindingScopeError(
                    f"Finding '{finding.finding_id}' belongs to agent "
                    f"'{finding.agent_id}', not '{agent_id}'"
                )

        risk_score = score_findings(findings)
        posture = AgentRiskPosture(
            agent_id=agent_id,
            risk_score=risk_score,
            risk_level=level_for_score(risk_score),
            finding_count=len(findings),
            baseline_at=baseline_at,
        )

        with self._lock:
            self._agent_postures[agent_id] = posture

        return posture

    def get_agent_posture(self, agent_id: str) -> AgentRiskPosture | None:
        """Return the last calculated enforcement posture for an agent."""
        with self._lock:
            return self._agent_postures.get(agent_id)

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
        """Clear process-local risk assessments and postures (useful for testing)."""
        with self._lock:
            self._assessments.clear()
            self._agent_postures.clear()

