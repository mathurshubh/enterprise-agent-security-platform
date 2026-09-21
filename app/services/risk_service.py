from datetime import datetime, timezone
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
    """Deterministic session-scoped risk derivation.

    ``RiskAssessment`` is derived state; ``Finding`` is the authoritative security
    evidence. Since M4-RISK this service **stores nothing**: it derives an assessment
    from findings on demand, for the runtime's per-request response and for the
    management plane's reads alike (ADR-027 Decision A).

    Assessment existence is therefore **evidence-defined** rather than
    execution-defined. An assessment exists for a ``(session_id, agent_id)`` pair
    exactly when findings exist for it. A session that executed and produced no
    findings has no assessment — the ``LOW``/0 record it used to carry was an
    artifact of the runtime writing one per request, not a statement about risk.

    This service is also **not** an agent-posture authority. It held a second
    implementation of agent-scoped posture until M5-B.5: ``RiskAggregator`` is the
    sole authority for enforcement posture, and what remains here answers "what does
    this session's evidence amount to", which the management plane reports and
    enforcement does not consult (ADR-024, ADR-026).
    """

    def __init__(self) -> None:
        self._lock = RLock()

    def assess_session(
        self,
        session_id: str,
        agent_id: str,
        findings: list[Finding],
    ) -> RiskAssessment:
        """Derive a deterministic risk assessment for one session and agent.

        Stores nothing (M4-RISK). Enforces strict session and agent isolation: all
        findings must belong to the given session_id and agent_id, because a
        mismatch means the caller assembled the security input incorrectly.
        """
        for finding in findings:
            if finding.session_id != session_id or finding.agent_id != agent_id:
                raise ValueError("All findings must belong to the requested session and agent")

        return self._derive(session_id, agent_id, findings)

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

    def _derive(
        self,
        session_id: str,
        agent_id: str,
        findings: list[Finding],
    ) -> RiskAssessment:
        """The single deterministic derivation both callers share.

        ``assessed_at`` is taken from the latest evidence rather than from the moment
        of the call, so two reads of unchanged evidence produce identical responses.
        A read-time clock would make a derived view non-reproducible and would report
        when it was looked at rather than what it reflects.
        """
        risk_score = score_findings(findings)
        observed_at = [
            finding.recorded_at or finding.created_at for finding in findings
        ]
        return RiskAssessment(
            session_id=session_id,
            agent_id=agent_id,
            risk_score=risk_score,
            risk_level=level_for_score(risk_score),
            finding_count=len(findings),
            assessed_at=max(observed_at) if observed_at else datetime.now(timezone.utc),
        )

    def reconstruct(self, findings: list[Finding]) -> list[RiskAssessment]:
        """Derive every assessment the supplied evidence defines.

        Existence is evidence-defined: one assessment per ``(session_id, agent_id)``
        pair that has findings, and none for pairs that do not. Ordered by
        ``session_id`` ascending, then ``agent_id``, so the collection is
        deterministic rather than inheriting the insertion order of whatever store
        happened to hold it.
        """
        grouped: dict[tuple[str, str], list[Finding]] = {}
        for finding in findings:
            grouped.setdefault((finding.session_id, finding.agent_id), []).append(finding)

        return [
            self._derive(session_id, agent_id, grouped[(session_id, agent_id)])
            for session_id, agent_id in sorted(grouped)
        ]

    def reconstruct_for_session(
        self,
        findings: list[Finding],
        session_id: str,
        agent_id: str | None = None,
    ) -> RiskAssessment | None:
        """Derive one session's assessment from the evidence supplied.

        Returns ``None`` when the session has no evidence, which the API reports as
        404. The ambiguity rule is unchanged in meaning and re-derived from its
        source: a session with findings from several agents cannot be assessed
        without naming one.

        Raises:
            AmbiguousAssessmentScopeError: the session holds evidence for more than
                one agent and no ``agent_id`` was supplied.
        """
        scoped = [f for f in findings if f.session_id == session_id]
        if agent_id is not None:
            scoped = [f for f in scoped if f.agent_id == agent_id]
            return self._derive(session_id, agent_id, scoped) if scoped else None

        agents = {f.agent_id for f in scoped}
        if not agents:
            return None
        if len(agents) > 1:
            raise AmbiguousAssessmentScopeError(
                f"Multiple agents have evidence for session '{session_id}'; "
                "agent_id is required"
            )
        return self._derive(session_id, agents.pop(), scoped)

