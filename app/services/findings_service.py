from datetime import datetime, timezone
from threading import RLock

from app.models.finding import Finding, FindingCategory, FindingStatus, Severity


class FindingsService:
    """In-memory findings repository service.

    The store also owns *when it accepted* each finding as evidence. That is a
    different question from ``Finding.created_at``, which detection rules set to a
    deterministic value so findings are reproducible. Enforcement needs the recording
    time: after a reinstatement, evidence accepted before that moment no longer drives
    enforcement, while evidence accepted afterwards does (M2b).

    ``recorded_at`` is internal to the evidence store and is not exposed by the API.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._findings: dict[str, Finding] = {}
        self._recorded_at: dict[str, datetime] = {}

    def record_finding(self, finding: Finding) -> Finding:
        """Record a single finding in the repository."""
        with self._lock:
            self._findings[finding.finding_id] = finding
            self._recorded_at.setdefault(
                finding.finding_id, datetime.now(timezone.utc)
            )
            return finding

    def record_findings(self, findings: list[Finding]) -> list[Finding]:
        """Record multiple findings in the repository."""
        with self._lock:
            now = datetime.now(timezone.utc)
            for finding in findings:
                self._findings[finding.finding_id] = finding
                self._recorded_at.setdefault(finding.finding_id, now)
            return findings

    def record_new_findings(self, findings: list[Finding]) -> list[Finding]:
        """Record only findings whose identifier is not already stored.

        Threshold detections re-derive the same finding on every later request in a
        session (see ``DetectionService.session_finding_id``). Storing the repeat
        would add a second piece of evidence for one behaviour and inflate cumulative
        risk, so already-known findings are skipped and the original record is kept.
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            recorded: list[Finding] = []
            for finding in findings:
                if finding.finding_id in self._findings:
                    continue
                self._findings[finding.finding_id] = finding
                self._recorded_at[finding.finding_id] = now
                recorded.append(finding)
            return recorded

    def list_findings(
        self,
        session_id: str | None = None,
        agent_id: str | None = None,
        severity: Severity | None = None,
        category: FindingCategory | None = None,
        status: FindingStatus | None = None,
        rule_id: str | None = None,
        recorded_after: datetime | None = None,
    ) -> list[Finding]:
        """Return findings matching optional filters in deterministic insertion order.

        ``recorded_after`` selects evidence this store accepted strictly after the given
        moment, which is how a reinstatement baseline separates historical evidence from
        evidence that still drives enforcement.
        """
        with self._lock:
            results = list(self._findings.values())
            if recorded_after is not None:
                results = [
                    finding
                    for finding in results
                    if self._recorded_at.get(finding.finding_id) is not None
                    and self._recorded_at[finding.finding_id] > recorded_after
                ]
            if session_id is not None:
                results = [f for f in results if f.session_id == session_id]
            if agent_id is not None:
                results = [f for f in results if f.agent_id == agent_id]
            if severity is not None:
                results = [f for f in results if f.severity == severity]
            if category is not None:
                results = [f for f in results if f.category == category]
            if status is not None:
                results = [f for f in results if f.status == status]
            if rule_id is not None:
                results = [f for f in results if f.rule_id == rule_id]
            return results

    def get_finding(self, finding_id: str) -> Finding | None:
        """Retrieve a finding by ID, or None if not found."""
        with self._lock:
            return self._findings.get(finding_id)

    def recorded_at(self, finding_id: str) -> datetime | None:
        """Return when this store accepted a finding as evidence."""
        with self._lock:
            return self._recorded_at.get(finding_id)

    def clear(self) -> None:
        """Clear all stored findings (useful for testing)."""
        with self._lock:
            self._findings.clear()
            self._recorded_at.clear()
