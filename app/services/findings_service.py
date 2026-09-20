from datetime import datetime, timezone
from threading import RLock

from app.models.finding import Finding, FindingCategory, FindingStatus, Severity
from app.models.watermark import UNASSIGNED_SEQUENCE, BaselineWatermark


class FindingsService:
    """In-memory findings repository service.

    The store also owns *when it accepted* each finding as evidence. That is a
    different question from ``Finding.created_at``, which detection rules set to a
    deterministic value so findings are reproducible. Enforcement needs the recording
    time: after a reinstatement, evidence accepted before that moment no longer drives
    enforcement, while evidence accepted afterwards does (M2b).

    ``recorded_at`` is internal to the evidence store and is not exposed by the API.
    """

    def __init__(
        self,
        initial_findings: list[Finding] | None = None,
        initial_recorded_at: dict[str, datetime] | None = None,
    ) -> None:
        self._lock = RLock()
        self._findings: dict[str, Finding] = {}
        self._recorded_at: dict[str, datetime] = {}
        self._agent_sequences: dict[str, int] = {}

        if initial_findings:
            with self._lock:
                for finding in initial_findings:
                    self._findings[finding.finding_id] = finding
                    if (
                        initial_recorded_at
                        and finding.finding_id in initial_recorded_at
                    ):
                        self._recorded_at[finding.finding_id] = (
                            initial_recorded_at[finding.finding_id]
                        )
                    else:
                        self._recorded_at.setdefault(
                            finding.finding_id, finding.created_at
                        )
                self._bootstrap_sequences()

    def _bootstrap_sequences(self) -> None:
        """Assign monotonic sequences to pre-M5 findings and reconstruct per-agent cursors (B-14).

        Idempotent: findings already having evidence_sequence >= 1 retain their sequence.
        Unassigned findings (evidence_sequence == 0) receive deterministic sequence numbers
        ordered by (recorded_at, created_at, finding_id).
        """
        by_agent: dict[str, list[Finding]] = {}
        for finding in self._findings.values():
            by_agent.setdefault(finding.agent_id, []).append(finding)

        for agent_id, agent_findings in by_agent.items():
            assigned_seqs = [
                f.evidence_sequence
                for f in agent_findings
                if f.evidence_sequence > UNASSIGNED_SEQUENCE
            ]
            max_seq = max(assigned_seqs, default=0)

            unassigned = [
                f
                for f in agent_findings
                if f.evidence_sequence == UNASSIGNED_SEQUENCE
            ]
            if unassigned:
                unassigned.sort(
                    key=lambda f: (
                        self._recorded_at.get(f.finding_id, f.created_at),
                        f.created_at,
                        f.finding_id,
                    )
                )
                for f in unassigned:
                    max_seq += 1
                    rec_at = self._recorded_at.get(f.finding_id, f.created_at)
                    updated = f.model_copy(
                        update={
                            "evidence_sequence": max_seq,
                            "recorded_at": rec_at,
                        }
                    )
                    self._findings[f.finding_id] = updated

            self._agent_sequences[agent_id] = max_seq

    def bootstrap_sequences(self) -> None:
        """Public entrypoint to run or re-run sequence bootstrap under lock."""
        with self._lock:
            self._bootstrap_sequences()

    def _next_sequence_for_agent(self, agent_id: str) -> int:
        seq = self._agent_sequences.get(agent_id, 0) + 1
        self._agent_sequences[agent_id] = seq
        return seq

    def _record_finding_locked(self, finding: Finding, now: datetime) -> Finding:
        if finding.finding_id in self._findings:
            existing = self._findings[finding.finding_id]
            assigned_seq = (
                existing.evidence_sequence
                if existing.evidence_sequence > UNASSIGNED_SEQUENCE
                else self._next_sequence_for_agent(finding.agent_id)
            )
            rec_at = self._recorded_at.get(existing.finding_id, now)
            assigned = finding.model_copy(
                update={
                    "evidence_sequence": assigned_seq,
                    "recorded_at": rec_at,
                }
            )
            self._findings[assigned.finding_id] = assigned
            self._recorded_at.setdefault(assigned.finding_id, now)
            return assigned

        assigned_seq = self._next_sequence_for_agent(finding.agent_id)
        assigned = finding.model_copy(
            update={"evidence_sequence": assigned_seq, "recorded_at": now}
        )
        self._findings[assigned.finding_id] = assigned
        self._recorded_at[assigned.finding_id] = now
        return assigned

    def record_finding(self, finding: Finding) -> Finding:
        """Record a single finding in the repository."""
        with self._lock:
            return self._record_finding_locked(
                finding, datetime.now(timezone.utc)
            )

    def record_findings(self, findings: list[Finding]) -> list[Finding]:
        """Record multiple findings in the repository."""
        with self._lock:
            now = datetime.now(timezone.utc)
            return [self._record_finding_locked(f, now) for f in findings]

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
                recorded.append(self._record_finding_locked(finding, now))
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

    def get_agent_sequence(self, agent_id: str) -> int:
        """Return the highest assigned sequence for an agent."""
        with self._lock:
            return self._agent_sequences.get(agent_id, 0)

    def capture_baseline(
        self,
        agent_id: str,
        baseline_at: datetime | None = None,
    ) -> BaselineWatermark:
        """Capture an immutable snapshot of an agent's baseline boundary (B-10).

        baseline_sequence is the highest authoritative sequence belonging to evidence
        at or before baseline_at.
        """
        with self._lock:
            at = baseline_at or datetime.now(timezone.utc)
            agent_findings = [
                f for f in self._findings.values() if f.agent_id == agent_id
            ]
            seqs = [
                f.evidence_sequence
                for f in agent_findings
                if self._recorded_at.get(f.finding_id, at) <= at
            ]
            highest_seq = max(seqs) if seqs else 0
            return BaselineWatermark(
                agent_id=agent_id,
                baseline_at=at,
                baseline_sequence=highest_seq,
            )

    def clear(self) -> None:
        """Clear all stored findings (useful for testing)."""
        with self._lock:
            self._findings.clear()
            self._recorded_at.clear()
            self._agent_sequences.clear()
