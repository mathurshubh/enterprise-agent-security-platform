"""Materialized single-agent risk posture projection engine (M5-B).

In-memory, thread-safe, bounded projection that maintains an agent's materialized
risk posture incrementally from authoritative findings and provides deterministic
reconstruction from authoritative evidence.
"""

import threading
from datetime import datetime, timezone
from typing import Collection, Sequence

from app.models.agent_risk_posture import AgentRiskPosture, PostureState
from app.models.finding import Finding, FindingStatus, Severity
from app.models.risk_assessment import RiskLevel
from app.models.watermark import UNASSIGNED_SEQUENCE, BaselineWatermark
from app.services.risk_service import SEVERITY_WEIGHTS, level_for_score

DEFAULT_RULE_VOCABULARY: frozenset[str] = frozenset(
    {
        "PROMPT_INJECTION",
        "SENSITIVE_FILE_ACCESS",
        "DATA_EXFILTRATION",
        "EXCESSIVE_DENIALS",
    }
)

ACTIVE_STATUSES: frozenset[FindingStatus] = frozenset(
    {FindingStatus.OPEN, FindingStatus.ACKNOWLEDGED}
)


class AgentRiskAggregate:
    """Thread-safe, bounded, in-memory projection of an agent's materialized risk posture (M5-B).

    Invariants enforced:
    - B-1: Projection Equivalence (HEALTHY posture matches deterministic rebuild)
    - B-2: Contiguous Application (cursor advances for every accepted post-baseline finding)
    - B-3: Idempotent Dedup (seq <= last_applied_sequence is a zero-mutation no-op)
    - B-4: Fail-Closed on Gap (seq > last_applied_sequence + 1 transitions to STALE)
    - B-5: Baseline Isolation (seq <= baseline_sequence is safely ignored)
    - B-7: Reconstructibility (full deterministic rebuild from findings & watermark)
    - B-9: Bounded Memory (zero finding-ID history; counts_by_rule bounded by rule vocabulary)
    - B-11: Cursor != Contribution (cursor tracks all findings; risk score tracks active findings)
    - B-13: Evidence Boundary Consistency (seq > baseline_seq with recorded_at <= baseline_at -> STALE)
    """

    def __init__(
        self,
        watermark: BaselineWatermark,
        rule_vocabulary: Collection[str] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self.agent_id: str = watermark.agent_id
        self.baseline_at: datetime | None = watermark.baseline_at
        self.baseline_sequence: int = watermark.baseline_sequence

        # Cursor initialized to baseline sequence
        self.last_applied_sequence: int = watermark.baseline_sequence

        # Bounded rule vocabulary (B-9)
        self._rule_vocabulary: frozenset[str] = (
            frozenset(rule_vocabulary)
            if rule_vocabulary is not None
            else DEFAULT_RULE_VOCABULARY
        )

        # Bounded derived state
        self.counts_by_severity: dict[Severity, int] = {s: 0 for s in Severity}
        self.counts_by_rule: dict[str, int] = {}
        self.finding_count: int = 0
        self.risk_score: int = 0
        self.risk_level: RiskLevel = RiskLevel.LOW

        self.state: PostureState = PostureState.HEALTHY
        self.posture_version: int = 1
        self.assessed_at: datetime = (
            watermark.baseline_at or datetime.now(timezone.utc)
        )

    def apply_finding(self, finding: Finding) -> bool:
        """Incrementally apply an authoritative finding to the projection.

        Returns True if applied, False if skipped (duplicate or pre-baseline).
        Transitions state to STALE if a gap or boundary anomaly is detected.
        """
        with self._lock:
            # 1. Agent identity validation
            if finding.agent_id != self.agent_id:
                raise ValueError(
                    f"Agent mismatch: finding belongs to '{finding.agent_id}', not '{self.agent_id}'"
                )

            # 2. Sequence validity validation
            if finding.evidence_sequence <= UNASSIGNED_SEQUENCE:
                raise ValueError(
                    f"Cannot apply unassigned finding (sequence={finding.evidence_sequence})"
                )

            # 3. Pre-baseline determination (B-5)
            # Findings at or before baseline sequence belong to a prior epoch; safely skip
            if finding.evidence_sequence <= self.baseline_sequence:
                return False

            # 3b. Duplicate determination (B-3 Idempotency)
            # Already applied sequence is an idempotent no-op (zero state mutation)
            if finding.evidence_sequence <= self.last_applied_sequence:
                return False

            # 4. B-13 Integrity validation:
            # For post-baseline evidence (seq > baseline_seq), recorded_at must be > baseline_at.
            # If a new finding has seq > baseline_seq but recorded_at <= baseline_at,
            # this is an integrity anomaly -> fail closed to STALE!
            finding_recorded_at = (
                finding.recorded_at
                if getattr(finding, "recorded_at", None) is not None
                else finding.created_at
            )
            if (
                self.baseline_at is not None
                and finding_recorded_at <= self.baseline_at
            ):
                self.state = PostureState.STALE
                self.assessed_at = datetime.now(timezone.utc)
                return False

            # 5. Sequence gap detection (B-4: Fail-closed on gap)
            expected_seq = self.last_applied_sequence + 1
            if finding.evidence_sequence > expected_seq:
                self.state = PostureState.STALE
                self.assessed_at = datetime.now(timezone.utc)
                return False

            # 6. Cursor advancement (B-2, B-11)
            # Every post-baseline authoritative finding advances the frontier
            self.last_applied_sequence = finding.evidence_sequence

            # 7. Active risk contribution (B-11)
            if finding.status in ACTIVE_STATUSES:
                self.counts_by_severity[finding.severity] += 1
                if finding.rule_id and finding.rule_id in self._rule_vocabulary:
                    self.counts_by_rule[finding.rule_id] = (
                        self.counts_by_rule.get(finding.rule_id, 0) + 1
                    )
                self.finding_count += 1
                self._recalculate_score_and_level()

            self.posture_version += 1
            self.assessed_at = datetime.now(timezone.utc)
            return True

    def rebuild_from_findings(
        self,
        authoritative_findings: Sequence[Finding],
        watermark: BaselineWatermark,
    ) -> None:
        """Deterministic full reconstruction from authoritative evidence (B-1, B-7).

        - Cursor derived from ALL post-baseline authoritative findings (B-11).
        - Risk contributions derived strictly from ACTIVE findings (B-11).
        - Rule counts bounded by registered rule vocabulary (B-9).
        """
        with self._lock:
            self.baseline_at = watermark.baseline_at
            self.baseline_sequence = watermark.baseline_sequence

            # Reset counts and bounded aggregates
            self.counts_by_severity = {s: 0 for s in Severity}
            self.counts_by_rule.clear()
            self.finding_count = 0

            # Filter post-baseline evidence
            post_baseline: list[Finding] = []
            for f in authoritative_findings:
                if f.agent_id != self.agent_id:
                    continue
                if f.evidence_sequence <= watermark.baseline_sequence:
                    continue
                f_rec = (
                    f.recorded_at
                    if getattr(f, "recorded_at", None) is not None
                    else f.created_at
                )
                if (
                    watermark.baseline_at is not None
                    and f_rec <= watermark.baseline_at
                ):
                    continue
                post_baseline.append(f)

            # 1. Cursor derived from ALL post-baseline authoritative findings
            if post_baseline:
                self.last_applied_sequence = max(
                    f.evidence_sequence for f in post_baseline
                )
            else:
                self.last_applied_sequence = watermark.baseline_sequence

            # 2. Risk contribution derived strictly from ACTIVE findings
            for f in post_baseline:
                if f.status in ACTIVE_STATUSES:
                    self.counts_by_severity[f.severity] += 1
                    if f.rule_id and f.rule_id in self._rule_vocabulary:
                        self.counts_by_rule[f.rule_id] = (
                            self.counts_by_rule.get(f.rule_id, 0) + 1
                        )
                    self.finding_count += 1

            self._recalculate_score_and_level()
            self.state = PostureState.HEALTHY
            self.posture_version += 1
            self.assessed_at = datetime.now(timezone.utc)

    def reset_to_baseline(self, watermark: BaselineWatermark) -> None:
        """Reset projection state to a new enforcement baseline (B-10)."""
        with self._lock:
            self.baseline_at = watermark.baseline_at
            self.baseline_sequence = watermark.baseline_sequence
            self.last_applied_sequence = watermark.baseline_sequence

            self.counts_by_severity = {s: 0 for s in Severity}
            self.counts_by_rule.clear()
            self.finding_count = 0
            self.risk_score = 0
            self.risk_level = RiskLevel.LOW

            self.state = PostureState.HEALTHY
            self.posture_version += 1
            self.assessed_at = watermark.baseline_at or datetime.now(timezone.utc)

    def mark_stale(self) -> None:
        """Explicitly transition projection to STALE (fail-closed)."""
        with self._lock:
            self.state = PostureState.STALE
            self.assessed_at = datetime.now(timezone.utc)
            self.posture_version += 1

    def snapshot(self) -> AgentRiskPosture:
        """Export an immutable snapshot for runtime consumption."""
        with self._lock:
            return AgentRiskPosture(
                agent_id=self.agent_id,
                state=self.state,
                risk_score=self.risk_score,
                risk_level=self.risk_level,
                finding_count=self.finding_count,
                baseline_at=self.baseline_at,
                baseline_sequence=self.baseline_sequence,
                last_applied_sequence=self.last_applied_sequence,
                counts_by_severity=dict(self.counts_by_severity),
                counts_by_rule=dict(self.counts_by_rule),
                posture_version=self.posture_version,
                assessed_at=self.assessed_at,
            )

    def _recalculate_score_and_level(self) -> None:
        """Calculate additive score and map onto risk level using frozen M5-A semantics."""
        self.risk_score = sum(
            self.counts_by_severity[sev] * SEVERITY_WEIGHTS[sev]
            for sev in Severity
        )
        self.risk_level = level_for_score(self.risk_score)
