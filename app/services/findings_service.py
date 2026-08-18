from threading import RLock

from app.models.finding import Finding, FindingCategory, FindingStatus, Severity


class FindingsService:
    """In-memory findings repository service."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._findings: dict[str, Finding] = {}

    def record_finding(self, finding: Finding) -> Finding:
        """Record a single finding in the repository."""
        with self._lock:
            self._findings[finding.finding_id] = finding
            return finding

    def record_findings(self, findings: list[Finding]) -> list[Finding]:
        """Record multiple findings in the repository."""
        with self._lock:
            for finding in findings:
                self._findings[finding.finding_id] = finding
            return findings

    def list_findings(
        self,
        session_id: str | None = None,
        agent_id: str | None = None,
        severity: Severity | None = None,
        category: FindingCategory | None = None,
        status: FindingStatus | None = None,
        rule_id: str | None = None,
    ) -> list[Finding]:
        """Return findings matching optional filters in deterministic insertion order."""
        with self._lock:
            results = list(self._findings.values())
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

    def clear(self) -> None:
        """Clear all stored findings (useful for testing)."""
        with self._lock:
            self._findings.clear()
